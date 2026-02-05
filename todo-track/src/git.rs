use std::collections::HashMap;
use std::path::Path;
use std::process::Command;

use crate::error::TodoTrackError;

/// Result of a git blame for a specific line.
#[derive(Debug, Clone)]
pub struct BlameInfo {
    pub author: String,
    pub date: String,
}

/// Run `git blame` on a specific file and line to get author and date info.
/// Uses the porcelain format for reliable parsing.
pub fn blame_line(
    repo_root: &Path,
    file_path: &str,
    line_number: usize,
) -> Result<BlameInfo, TodoTrackError> {
    let line_spec = format!("{},{}", line_number, line_number);

    let output = Command::new("git")
        .args([
            "blame",
            "--porcelain",
            "-L",
            &line_spec,
            "--",
            file_path,
        ])
        .current_dir(repo_root)
        .output()
        .map_err(|e| TodoTrackError::GitBlame {
            file: file_path.to_string(),
            reason: format!("failed to execute git blame: {}", e),
        })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(TodoTrackError::GitBlame {
            file: file_path.to_string(),
            reason: stderr.to_string(),
        });
    }

    parse_porcelain_blame(&String::from_utf8_lossy(&output.stdout))
        .ok_or_else(|| TodoTrackError::GitBlame {
            file: file_path.to_string(),
            reason: "failed to parse blame output".to_string(),
        })
}

/// Blame an entire file once and return BlameInfo for all requested lines.
/// Much faster than calling blame_line N times (1 process spawn vs N).
pub fn blame_file_lines(
    repo_root: &Path,
    file_path: &str,
    line_numbers: &[usize],
) -> Result<HashMap<usize, BlameInfo>, TodoTrackError> {
    if line_numbers.is_empty() {
        return Ok(HashMap::new());
    }

    let output = Command::new("git")
        .args(["blame", "--porcelain", "--", file_path])
        .current_dir(repo_root)
        .output()
        .map_err(|e| TodoTrackError::GitBlame {
            file: file_path.to_string(),
            reason: format!("failed to execute git blame: {}", e),
        })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(TodoTrackError::GitBlame {
            file: file_path.to_string(),
            reason: stderr.to_string(),
        });
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let wanted: std::collections::HashSet<usize> = line_numbers.iter().copied().collect();
    let mut results = HashMap::new();

    // Parse porcelain output: each block starts with a commit hash line
    // containing the original line number and current line number.
    let mut current_line_num: Option<usize> = None;
    let mut current_author = String::from("Unknown");
    let mut current_date = String::from("Unknown");

    for line in stdout.lines() {
        // Commit line: <hash> <orig-line> <final-line> [<num-lines>]
        if line.len() >= 40 && line.chars().take(40).all(|c| c.is_ascii_hexdigit()) {
            // Save previous block if it was a wanted line
            if let Some(ln) = current_line_num {
                if wanted.contains(&ln) {
                    results.insert(ln, BlameInfo {
                        author: current_author.clone(),
                        date: current_date.clone(),
                    });
                }
            }
            // Parse the final line number (3rd field)
            let parts: Vec<&str> = line.split_whitespace().collect();
            current_line_num = parts.get(2).and_then(|s| s.parse().ok());
            current_author = String::from("Unknown");
            current_date = String::from("Unknown");
        } else if let Some(val) = line.strip_prefix("author ") {
            current_author = val.trim().to_string();
        } else if let Some(val) = line.strip_prefix("author-time ") {
            if let Ok(ts) = val.trim().parse::<i64>() {
                if let Some(dt) = chrono::DateTime::from_timestamp(ts, 0) {
                    current_date = dt.format("%Y-%m-%d").to_string();
                }
            }
        }
    }

    // Don't forget the last block
    if let Some(ln) = current_line_num {
        if wanted.contains(&ln) {
            results.insert(ln, BlameInfo {
                author: current_author,
                date: current_date,
            });
        }
    }

    Ok(results)
}

/// Parse a single-block porcelain blame output into BlameInfo.
fn parse_porcelain_blame(stdout: &str) -> Option<BlameInfo> {
    let mut author = String::from("Unknown");
    let mut date = String::from("Unknown");

    for line in stdout.lines() {
        if let Some(val) = line.strip_prefix("author ") {
            author = val.trim().to_string();
        } else if let Some(val) = line.strip_prefix("author-time ") {
            if let Ok(ts) = val.trim().parse::<i64>() {
                if let Some(dt) = chrono::DateTime::from_timestamp(ts, 0) {
                    date = dt.format("%Y-%m-%d").to_string();
                }
            }
        }
    }

    Some(BlameInfo { author, date })
}

/// Check if the given path is inside a git repository.
pub fn is_git_repo(path: &Path) -> bool {
    Command::new("git")
        .args(["rev-parse", "--is-inside-work-tree"])
        .current_dir(path)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}
