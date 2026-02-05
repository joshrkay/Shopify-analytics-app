use thiserror::Error;

#[derive(Error, Debug)]
pub enum TodoTrackError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Database error: {0}")]
    Database(#[from] rusqlite::Error),

    #[error("Regex error: {0}")]
    Regex(#[from] regex::Error),

    #[error("Path error: {0}")]
    InvalidPath(String),

    #[error("No snapshots found. Run 'todo-track scan' first.")]
    NoSnapshots,

    #[error("Git blame failed for {file}: {reason}")]
    GitBlame { file: String, reason: String },
}
