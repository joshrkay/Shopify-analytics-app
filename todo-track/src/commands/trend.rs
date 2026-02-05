use anyhow::{Context, Result};
use colored::Colorize;
use std::path::Path;

use crate::error::TodoTrackError;
use crate::storage;

/// Execute the `trend` command: show historical snapshots with % change.
pub fn run() -> Result<()> {
    // Look for the DB in the current directory
    let root = Path::new(".")
        .canonicalize()
        .context("Failed to resolve current directory")?;

    let conn = storage::open_db(&root).context("Failed to open database")?;
    let snapshots = storage::get_snapshots(&conn)?;

    if snapshots.is_empty() {
        return Err(TodoTrackError::NoSnapshots.into());
    }

    // Print header
    println!(
        "  {:<6} {:<22} {:<8} {}",
        "#".bold(),
        "Timestamp".bold(),
        "TODOs".bold(),
        "Change".bold()
    );
    println!("  {}", "-".repeat(56));

    let mut prev_count: Option<i64> = None;

    for snap in &snapshots {
        let change_str = match prev_count {
            None => "  --".dimmed().to_string(),
            Some(prev) => {
                if prev == 0 {
                    if snap.todo_count > 0 {
                        format!("  {} +{}", "\u{2191}", snap.todo_count)
                            .red()
                            .to_string()
                    } else {
                        "  --".dimmed().to_string()
                    }
                } else {
                    let diff = snap.todo_count - prev;
                    let pct = ((diff as f64) / (prev as f64) * 100.0).round() as i64;
                    if diff > 0 {
                        format!("  \u{2191} +{} ({:+}%)", diff, pct)
                            .red()
                            .to_string()
                    } else if diff < 0 {
                        format!("  \u{2193} {} ({}%)", diff, pct)
                            .green()
                            .to_string()
                    } else {
                        "  = (0%)".dimmed().to_string()
                    }
                }
            }
        };

        let count_colored = if snap.todo_count == 0 {
            format!("{:<8}", snap.todo_count).green()
        } else if snap.todo_count <= 10 {
            format!("{:<8}", snap.todo_count).yellow()
        } else {
            format!("{:<8}", snap.todo_count).red()
        };

        println!(
            "  {:<6} {:<22} {} {}",
            snap.id, snap.timestamp, count_colored, change_str
        );

        prev_count = Some(snap.todo_count);
    }

    println!();
    println!(
        "  {} snapshots total",
        snapshots.len().to_string().bold()
    );

    Ok(())
}
