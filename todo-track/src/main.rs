mod cli;
mod commands;
mod error;
mod git;
mod parser;
mod scanner;
mod storage;

use anyhow::Result;
use clap::Parser;

use cli::{Cli, Command};

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Command::Scan { path } => {
            commands::scan::run(&path)?;
        }
        Command::List {
            path,
            oldest,
            blame,
        } => {
            commands::list::run(&path, oldest, blame)?;
        }
        Command::Trend => {
            commands::trend::run()?;
        }
        Command::Check { max } => {
            commands::check::run(max)?;
        }
    }

    Ok(())
}
