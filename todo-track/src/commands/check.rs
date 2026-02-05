use std::path::Path;
use std::process;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::error::TodoTrackError;
use crate::storage;

/// Execute the `check` command: CI gate that fails if TODO count exceeds max.
pub fn run(max: usize) -> Result<()> {
    let root = Path::new(".")
        .canonicalize()
        .context("Failed to resolve current directory")?;

    let conn = storage::open_db(&root).context("Failed to open database")?;

    let count = storage::get_latest_todo_count(&conn)?
        .ok_or(TodoTrackError::NoSnapshots)?;

    let count_usize = count as usize;

    println!(
        "TODO count: {} (max allowed: {})",
        if count_usize > max {
            count.to_string().red().bold()
        } else {
            count.to_string().green().bold()
        },
        max
    );

    if count_usize > max {
        println!(
            "\n{}",
            format!(
                "FAIL: {} TODOs exceed maximum of {}. Reduce by {} to pass.",
                count_usize,
                max,
                count_usize - max
            )
            .red()
            .bold()
        );
        process::exit(1);
    } else {
        println!(
            "\n{}",
            format!(
                "PASS: {} TODOs within limit of {}.",
                count_usize, max
            )
            .green()
            .bold()
        );
    }

    Ok(())
}
