use std::collections::HashSet;
use std::path::Path;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::scanner;
use crate::storage;

/// Execute the `scan` command: scan for TODOs, print them, store snapshot.
pub fn run(path: &Path) -> Result<()> {
    let root = path
        .canonicalize()
        .with_context(|| format!("Invalid scan path: {}", path.display()))?;

    println!(
        "{}",
        format!("Scanning {}...", root.display()).dimmed()
    );

    let result = scanner::scan_directory(&root);
    let todo_count = result.todos.len();

    // Count unique files with TODOs
    let files_with_todos: HashSet<_> = result
        .todos
        .iter()
        .map(|t| t.file_path.clone())
        .collect();
    let file_count = files_with_todos.len();

    // Print each TODO
    for todo in &result.todos {
        let location = format!(
            "{}:{}",
            todo.file_path.display(),
            todo.item.line_number
        )
        .bold();

        let keyword = match todo.item.keyword.as_str() {
            "TODO" => todo.item.keyword.yellow(),
            "FIXME" => todo.item.keyword.red(),
            "HACK" => todo.item.keyword.magenta(),
            "XXX" => todo.item.keyword.red().bold(),
            _ => todo.item.keyword.normal(),
        };

        let mut extras = Vec::new();
        if let Some(ref author) = todo.item.author {
            extras.push(format!("({})", author));
        }
        if let Some(ref issue) = todo.item.issue_ref {
            extras.push(issue.clone());
        }

        let extras_str = if extras.is_empty() {
            String::new()
        } else {
            format!(" {}", extras.join(" ").dimmed())
        };

        println!(
            "  {} {} {}{}",
            location, keyword, todo.item.description, extras_str
        );
    }

    // Summary line with color based on count
    let summary = format!(
        "Found {} TODOs across {} files",
        todo_count, file_count
    );
    let colored_summary = if todo_count == 0 {
        summary.green()
    } else if todo_count <= 10 {
        summary.yellow()
    } else {
        summary.red()
    };
    println!("\n{}", colored_summary);
    println!(
        "{}",
        format!(
            "({} files scanned, {} skipped)",
            result.files_scanned, result.files_skipped
        )
        .dimmed()
    );

    // Save snapshot to SQLite
    let conn = storage::open_db(&root).context("Failed to open database")?;
    let snapshot_id =
        storage::save_snapshot(&conn, &result.todos).context("Failed to save snapshot")?;

    println!(
        "{}",
        format!("Snapshot #{} saved.", snapshot_id).green()
    );

    Ok(())
}
