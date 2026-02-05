use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::parser::{self, TodoItem};

/// Maximum file size to scan (1 MB). Files larger than this are skipped.
const MAX_FILE_SIZE: u64 = 1_048_576;

/// Directories to always skip during scanning.
const SKIP_DIRS: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "vendor",
    ".todo-track",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
];

/// A TODO found in a specific file, combining the parsed item with its file path.
#[derive(Debug, Clone)]
pub struct FileTodo {
    pub file_path: PathBuf,
    pub item: TodoItem,
}

/// Result of scanning a directory tree.
#[derive(Debug)]
pub struct ScanResult {
    pub todos: Vec<FileTodo>,
    pub files_scanned: usize,
    pub files_skipped: usize,
}

/// Check if a directory entry should be skipped.
fn should_skip_dir(dir_name: &str) -> bool {
    SKIP_DIRS.contains(&dir_name)
}

/// Scan a directory tree for TODO comments.
/// Skips files > MAX_FILE_SIZE, non-UTF-8 files, and known non-source directories.
pub fn scan_directory(root: &Path) -> ScanResult {
    let mut todos = Vec::new();
    let mut files_scanned: usize = 0;
    let mut files_skipped: usize = 0;

    let walker = WalkDir::new(root).follow_links(false).into_iter();

    for entry in walker.filter_entry(|e| {
        if e.file_type().is_dir() {
            if let Some(name) = e.file_name().to_str() {
                return !should_skip_dir(name);
            }
        }
        true
    }) {
        let entry = match entry {
            Ok(e) => e,
            Err(_) => {
                files_skipped += 1;
                continue;
            }
        };

        if !entry.file_type().is_file() {
            continue;
        }

        let path = entry.path();

        // Skip files larger than MAX_FILE_SIZE
        let metadata = match fs::metadata(path) {
            Ok(m) => m,
            Err(_) => {
                files_skipped += 1;
                continue;
            }
        };

        if metadata.len() > MAX_FILE_SIZE {
            files_skipped += 1;
            continue;
        }

        // Read the file, skipping non-UTF-8 files gracefully
        let content = match fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => {
                files_skipped += 1;
                continue;
            }
        };

        files_scanned += 1;

        let items = parser::parse_content(&content);
        for item in items {
            // Store a path relative to the root for cleaner output
            let relative = path
                .strip_prefix(root)
                .unwrap_or(path)
                .to_path_buf();
            todos.push(FileTodo {
                file_path: relative,
                item,
            });
        }
    }

    ScanResult {
        todos,
        files_scanned,
        files_skipped,
    }
}
