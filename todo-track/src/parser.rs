use regex::Regex;
use std::sync::LazyLock;

/// A parsed TODO item extracted from a single line of source code.
#[derive(Debug, Clone, PartialEq)]
pub struct TodoItem {
    /// The line number (1-indexed) in the file
    pub line_number: usize,
    /// The keyword that was matched (TODO, FIXME, HACK, XXX)
    pub keyword: String,
    /// Optional author extracted from e.g. TODO(alice):
    pub author: Option<String>,
    /// Optional issue reference extracted from #123-style patterns
    pub issue_ref: Option<String>,
    /// The description text after the keyword
    pub description: String,
}

// Comment markers that indicate a line contains a comment
const COMMENT_MARKERS: &[&str] = &["//", "#", "/*", "<!--", "*", "--"];

static TODO_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(TODO|FIXME|HACK|XXX)\b(?:\(([^)]+)\))?:?\s*(.+)")
        .expect("TODO_RE pattern must be valid")
});

static ISSUE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"#(\d+)").expect("ISSUE_RE pattern must be valid")
});

/// Check whether a line contains a comment marker.
fn line_has_comment_marker(line: &str) -> bool {
    let trimmed = line.trim();
    COMMENT_MARKERS.iter().any(|marker| trimmed.contains(marker))
}

/// Parse a single line of text and return a TodoItem if it contains a TODO-like comment.
/// This is a pure function with no IO.
pub fn parse_line(line: &str, line_number: usize) -> Option<TodoItem> {
    if !line_has_comment_marker(line) {
        return None;
    }

    let caps = TODO_RE.captures(line)?;

    let keyword = caps.get(1)?.as_str().to_uppercase();
    let author = caps.get(2).map(|m| m.as_str().trim().to_string());
    let raw_description = caps.get(3)?.as_str().trim().to_string();

    let issue_ref = ISSUE_RE
        .captures(&raw_description)
        .map(|c| format!("#{}", &c[1]));

    Some(TodoItem {
        line_number,
        keyword,
        author,
        issue_ref,
        description: raw_description,
    })
}

/// Parse all lines in a string and return all found TodoItems.
/// This is a pure function with no IO.
pub fn parse_content(content: &str) -> Vec<TodoItem> {
    content
        .lines()
        .enumerate()
        .filter_map(|(idx, line)| parse_line(line, idx + 1))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_todo() {
        let line = "// TODO: fix this later";
        let item = parse_line(line, 1).unwrap();
        assert_eq!(item.keyword, "TODO");
        assert_eq!(item.description, "fix this later");
        assert!(item.author.is_none());
        assert!(item.issue_ref.is_none());
    }

    #[test]
    fn test_todo_with_author() {
        let line = "// TODO(alice): refactor this";
        let item = parse_line(line, 5).unwrap();
        assert_eq!(item.keyword, "TODO");
        assert_eq!(item.author.as_deref(), Some("alice"));
        assert_eq!(item.description, "refactor this");
    }

    #[test]
    fn test_fixme_with_issue() {
        let line = "# FIXME: broken sorting see #42";
        let item = parse_line(line, 10).unwrap();
        assert_eq!(item.keyword, "FIXME");
        assert_eq!(item.issue_ref.as_deref(), Some("#42"));
    }

    #[test]
    fn test_hack_comment() {
        let line = "/* HACK: temporary workaround */";
        let item = parse_line(line, 3).unwrap();
        assert_eq!(item.keyword, "HACK");
        assert_eq!(item.description, "temporary workaround */");
    }

    #[test]
    fn test_xxx_comment() {
        let line = "// XXX: needs review";
        let item = parse_line(line, 1).unwrap();
        assert_eq!(item.keyword, "XXX");
    }

    #[test]
    fn test_case_insensitive() {
        let line = "// todo: lowercase works";
        let item = parse_line(line, 1).unwrap();
        assert_eq!(item.keyword, "TODO");
    }

    #[test]
    fn test_no_comment_marker() {
        let line = "let x = TODO something";
        assert!(parse_line(line, 1).is_none());
    }

    #[test]
    fn test_parse_content() {
        let content = "fn main() {\n    // TODO: first thing\n    let x = 1;\n    // FIXME: second thing\n}\n";
        let items = parse_content(content);
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].line_number, 2);
        assert_eq!(items[1].line_number, 4);
    }

    #[test]
    fn test_no_false_positive_substring() {
        // "TodoItem" should NOT match — "Todo" is a substring, not the word TODO
        let line = "/// A parsed TodoItem extracted from source code.";
        assert!(parse_line(line, 1).is_none());
    }

    #[test]
    fn test_html_comment() {
        let line = "<!-- TODO: fix layout -->";
        let item = parse_line(line, 1).unwrap();
        assert_eq!(item.keyword, "TODO");
    }
}
