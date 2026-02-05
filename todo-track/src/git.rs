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

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut author = String::from("Unknown");
    let mut date = String::from("Unknown");

    for line in stdout.lines() {
        if let Some(val) = line.strip_prefix("author ") {
            author = val.trim().to_string();
        } else if let Some(val) = line.strip_prefix("author-time ") {
            // author-time is a Unix timestamp; convert to human-readable
            if let Ok(ts) = val.trim().parse::<i64>() {
                let dt = chrono::DateTime::from_timestamp(ts, 0);
                if let Some(dt) = dt {
                    date = dt.format("%Y-%m-%d").to_string();
                }
            }
        }
    }

    Ok(BlameInfo { author, date })
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
