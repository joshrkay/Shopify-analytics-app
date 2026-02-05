use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;
use rusqlite::{params, Connection};

use crate::error::TodoTrackError;
use crate::scanner::FileTodo;

/// A snapshot row from the database.
#[derive(Debug, Clone)]
pub struct Snapshot {
    pub id: i64,
    pub timestamp: String,
    pub todo_count: i64,
}

/// A todo row from the database, including optional git blame info.
#[derive(Debug, Clone)]
pub struct StoredTodo {
    pub id: i64,
    pub snapshot_id: i64,
    pub file_path: String,
    pub line_number: i64,
    pub keyword: String,
    pub author: Option<String>,
    pub issue_ref: Option<String>,
    pub description: String,
    pub git_author: Option<String>,
    pub git_date: Option<String>,
}

/// Get the path to the database file, creating the directory if needed.
pub fn db_path(root: &Path) -> Result<PathBuf, TodoTrackError> {
    let dir = root.join(".todo-track");
    fs::create_dir_all(&dir)?;
    Ok(dir.join("db.sqlite"))
}

/// Open (or create) the SQLite database and run migrations.
pub fn open_db(root: &Path) -> Result<Connection, TodoTrackError> {
    let path = db_path(root)?;
    let conn = Connection::open(path)?;

    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            todo_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY,
            snapshot_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            author TEXT,
            issue_ref TEXT,
            description TEXT NOT NULL,
            git_author TEXT,
            git_date TEXT,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        );",
    )?;

    Ok(conn)
}

/// Insert a new snapshot and all its TODOs. Returns the snapshot ID.
/// Uses an explicit transaction for bulk inserts (10-100x faster).
pub fn save_snapshot(
    conn: &Connection,
    todos: &[FileTodo],
) -> Result<i64, TodoTrackError> {
    let timestamp = Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let todo_count = todos.len() as i64;

    conn.execute("BEGIN", [])?;

    let result = (|| -> Result<i64, TodoTrackError> {
        conn.execute(
            "INSERT INTO snapshots (timestamp, todo_count) VALUES (?1, ?2)",
            params![timestamp, todo_count],
        )?;

        let snapshot_id = conn.last_insert_rowid();

        let mut stmt = conn.prepare(
            "INSERT INTO todos (snapshot_id, file_path, line_number, keyword, author, issue_ref, description)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        )?;

        for ft in todos {
            stmt.execute(params![
                snapshot_id,
                ft.file_path.to_string_lossy().to_string(),
                ft.item.line_number as i64,
                ft.item.keyword,
                ft.item.author,
                ft.item.issue_ref,
                ft.item.description,
            ])?;
        }

        Ok(snapshot_id)
    })();

    match result {
        Ok(id) => {
            conn.execute("COMMIT", [])?;
            Ok(id)
        }
        Err(e) => {
            let _ = conn.execute("ROLLBACK", []);
            Err(e)
        }
    }
}

/// Update git blame info for a specific todo row.
pub fn update_git_blame(
    conn: &Connection,
    todo_id: i64,
    git_author: &str,
    git_date: &str,
) -> Result<(), TodoTrackError> {
    conn.execute(
        "UPDATE todos SET git_author = ?1, git_date = ?2 WHERE id = ?3",
        params![git_author, git_date, todo_id],
    )?;
    Ok(())
}

/// Get all snapshots ordered by timestamp (newest first).
pub fn get_snapshots(conn: &Connection) -> Result<Vec<Snapshot>, TodoTrackError> {
    let mut stmt = conn.prepare(
        "SELECT id, timestamp, todo_count FROM snapshots ORDER BY id ASC",
    )?;

    let rows = stmt.query_map([], |row| {
        Ok(Snapshot {
            id: row.get(0)?,
            timestamp: row.get(1)?,
            todo_count: row.get(2)?,
        })
    })?;

    let mut snapshots = Vec::new();
    for row in rows {
        snapshots.push(row?);
    }
    Ok(snapshots)
}

/// Get the latest snapshot.
pub fn get_latest_snapshot(conn: &Connection) -> Result<Option<Snapshot>, TodoTrackError> {
    let mut stmt = conn.prepare(
        "SELECT id, timestamp, todo_count FROM snapshots ORDER BY id DESC LIMIT 1",
    )?;

    let mut rows = stmt.query_map([], |row| {
        Ok(Snapshot {
            id: row.get(0)?,
            timestamp: row.get(1)?,
            todo_count: row.get(2)?,
        })
    })?;

    match rows.next() {
        Some(row) => Ok(Some(row?)),
        None => Ok(None),
    }
}

/// Get all todos for a given snapshot.
pub fn get_todos_for_snapshot(
    conn: &Connection,
    snapshot_id: i64,
) -> Result<Vec<StoredTodo>, TodoTrackError> {
    let mut stmt = conn.prepare(
        "SELECT id, snapshot_id, file_path, line_number, keyword, author, issue_ref, description, git_author, git_date
         FROM todos
         WHERE snapshot_id = ?1
         ORDER BY file_path, line_number",
    )?;

    let rows = stmt.query_map(params![snapshot_id], |row| {
        Ok(StoredTodo {
            id: row.get(0)?,
            snapshot_id: row.get(1)?,
            file_path: row.get(2)?,
            line_number: row.get(3)?,
            keyword: row.get(4)?,
            author: row.get(5)?,
            issue_ref: row.get(6)?,
            description: row.get(7)?,
            git_author: row.get(8)?,
            git_date: row.get(9)?,
        })
    })?;

    let mut todos = Vec::new();
    for row in rows {
        todos.push(row?);
    }
    Ok(todos)
}

/// Get the latest TODO count from the most recent snapshot.
pub fn get_latest_todo_count(conn: &Connection) -> Result<Option<i64>, TodoTrackError> {
    match get_latest_snapshot(conn)? {
        Some(s) => Ok(Some(s.todo_count)),
        None => Ok(None),
    }
}
