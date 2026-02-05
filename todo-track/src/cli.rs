use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(name = "todo-track")]
#[command(about = "Track TODO/FIXME/HACK/XXX comments across your codebase")]
#[command(version)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// Scan files for TODO comments and store a snapshot
    Scan {
        /// Path to scan (defaults to current directory)
        #[arg(default_value = ".")]
        path: PathBuf,
    },

    /// List TODOs from the most recent snapshot
    List {
        /// Path to scan (defaults to current directory)
        #[arg(default_value = ".")]
        path: PathBuf,

        /// Show only the N oldest TODOs by git blame date
        #[arg(long)]
        oldest: Option<usize>,

        /// Run git blame to show authorship info
        #[arg(long, default_value_t = false)]
        blame: bool,
    },

    /// Show historical trend of TODO counts
    Trend,

    /// CI check: exit 1 if TODO count exceeds max
    Check {
        /// Maximum allowed TODO count
        #[arg(long)]
        max: usize,
    },
}
