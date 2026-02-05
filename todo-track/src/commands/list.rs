use std::path::Path;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::error::TodoTrackError;
use crate::git;
use crate::storage::{self, StoredTodo};

/// Execute the `list` command: list TODOs from the latest snapshot.
pub fn run(path: &Path, oldest: Option<usize>, blame: bool) -> Result<()> {
    let root = path
        .canonicalize()
        .with_context(|| format!("Invalid path: {}", path.display()))?;

    let conn = storage::open_db(&root).context("Failed to open database")?;

    let snapshot = storage::get_latest_snapshot(&conn)?
        .ok_or(TodoTrackError::NoSnapshots)?;

    let mut todos = storage::get_todos_for_snapshot(&conn, snapshot.id)?;

    println!(
        "{}",
        format!(
            "Snapshot #{} ({}) - {} TODOs",
            snapshot.id, snapshot.timestamp, snapshot.todo_count
        )
        .dimmed()
    );
    println!();

    // If --blame is passed, run git blame for each TODO
    if blame && git::is_git_repo(&root) {
        println!("{}", "Running git blame (this may take a moment)...".dimmed());
        for todo in &mut todos {
            match git::blame_line(&root, &todo.file_path, todo.line_number as usize) {
                Ok(info) => {
                    // Update in-memory
                    todo.git_author = Some(info.author.clone());
                    todo.git_date = Some(info.date.clone());
                    // Persist to DB
                    let _ = storage::update_git_blame(
                        &conn,
                        todo.id,
                        &info.author,
                        &info.date,
                    );
                }
                Err(_) => {
                    // Silently skip blame failures for individual lines
                }
            }
        }
        println!();
    }

    // If --oldest N is specified, sort by git_date ascending and take N
    if let Some(n) = oldest {
        if !blame {
            eprintln!(
                "{}",
                "Warning: --oldest works best with --blame to get git dates.".yellow()
            );
            eprintln!(
                "{}",
                "Showing TODOs without date sorting.\n".yellow()
            );
        } else {
            todos.sort_by(|a, b| {
                let date_a = a.git_date.as_deref().unwrap_or("9999-99-99");
                let date_b = b.git_date.as_deref().unwrap_or("9999-99-99");
                date_a.cmp(date_b)
            });
        }
        todos.truncate(n);
    }

    // Print each TODO
    for todo in &todos {
        print_todo(todo);
    }

    if todos.is_empty() {
        println!("{}", "No TODOs found.".green());
    }

    Ok(())
}

fn print_todo(todo: &StoredTodo) {
    let location = format!("{}:{}", todo.file_path, todo.line_number).bold();

    let keyword = match todo.keyword.as_str() {
        "TODO" => todo.keyword.yellow(),
        "FIXME" => todo.keyword.red(),
        "HACK" => todo.keyword.magenta(),
        "XXX" => todo.keyword.red().bold(),
        _ => todo.keyword.normal(),
    };

    let mut parts = vec![format!("  {} {} {}", location, keyword, todo.description)];

    if let Some(ref author) = todo.author {
        parts.push(format!(" ({})", author).dimmed().to_string());
    }
    if let Some(ref issue) = todo.issue_ref {
        parts.push(format!(" {}", issue).cyan().to_string());
    }

    print!("{}", parts.join(""));

    // Show blame info if available
    if todo.git_author.is_some() || todo.git_date.is_some() {
        let blame_author = todo
            .git_author
            .as_deref()
            .unwrap_or("?");
        let blame_date = todo
            .git_date
            .as_deref()
            .unwrap_or("?");
        print!(
            " {}",
            format!("[{} on {}]", blame_author, blame_date).dimmed()
        );
    }

    println!();
}
