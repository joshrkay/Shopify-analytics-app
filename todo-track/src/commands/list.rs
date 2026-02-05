use std::collections::HashMap;
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

    // If --blame is passed, batch git blame by file (1 spawn per file, not per TODO)
    if blame && git::is_git_repo(&root) {
        println!("{}", "Running git blame (this may take a moment)...".dimmed());

        // Group TODOs by file path
        let mut by_file: HashMap<String, Vec<usize>> = HashMap::new();
        for (idx, todo) in todos.iter().enumerate() {
            by_file
                .entry(todo.file_path.clone())
                .or_default()
                .push(idx);
        }

        // Blame each file once, then distribute results
        for (file_path, indices) in &by_file {
            let line_numbers: Vec<usize> = indices
                .iter()
                .map(|&i| todos[i].line_number as usize)
                .collect();

            match git::blame_file_lines(&root, file_path, &line_numbers) {
                Ok(blame_map) => {
                    for &idx in indices {
                        let ln = todos[idx].line_number as usize;
                        if let Some(info) = blame_map.get(&ln) {
                            todos[idx].git_author = Some(info.author.clone());
                            todos[idx].git_date = Some(info.date.clone());
                            if let Err(e) = storage::update_git_blame(
                                &conn,
                                todos[idx].id,
                                &info.author,
                                &info.date,
                            ) {
                                eprintln!("{}", format!("Warning: failed to save blame for {}:{}: {}", file_path, ln, e).dimmed());
                            }
                        }
                    }
                }
                Err(_) => {
                    // Skip blame failures for individual files
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
