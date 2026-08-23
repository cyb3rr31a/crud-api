import sqlite3
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

DATABASE_FILE = "tasks.db"

# --- Database Connection Helper ---
def get_db_connection() -> sqlite3.Connection:
    """Creates a database connection with dictionary-like row access"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- Database Initialization
def init_db():
    """Creates the tasks table and seeds initial records if empty"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done BOOLEAN NOT NULL DEFAULT 0
            )
        """)

        # Check if table is empty
        cursor.execute("SELECT COUNT(*) AS count FROM tasks")
        count = cursor.fetchone()["count"]

        # Seed only on first run
        if count == 0:
            initial_tasks = [
                ("Buy groceries", 0),
                ("Walk the dog", 1),
                ("Clean my room", 0)
            ]
            cursor.executemany(
                "INSERT INTO tasks (title, done) VALUES (?, ?)",
                initial_tasks
            )
            conn.commit()

# --- Lifespan Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Task API", version="2.0.0", lifespan=lifespan)

# --- Schemas ---
class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, examples=["Buy groceries"])
    done: bool = Field(default=False, examples=[True])

class TaskCreate(TaskBase):
    pass
    
class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    done: Optional[bool] = None

class Task(TaskBase):
    id: int

# --- Endpoints ---
@app.get("/", tags=["General"])
async def root():
    return {
        "name": 'Task API',
        "version": "2.0",
        "endpoints": ["/tasks", "/tasks/{id}", "stats", "/health"]
    }

@app.get("/health", tags=["General"])
async def health():
    return {"status": "ok"}

# Read all tasks
@app.get("/tasks", response_model=List[Task], tags=["Tasks"])
async def get_tasks(
    search: Optional[str] = Query(None, description="Search term for task title"),
    done: Optional[bool] = Query(None, description="Filter by completion status")
):
    query = "SELECT id, title, done FROM tasks WHERE 1=1"
    params = []

    # Search filtering using SQL LIKE
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")

    # Optional Extra: Done status filtering
    if done is not None:
        query += " AND done = ?"
        params.append(1 if done else 0)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [
            Task(id=row["id"], title=row["title"], done=bool(row["done"]))
            for row in rows
        ]

# Read one task
@app.get("/tasks/{task_id}", response_model=List[Task], tags=["Tasks"])
async def get_task(task_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title. done FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail = "Task not found"
            )

        return Task(id=row["id"], title=row["title"], done=bool(row["done"]))

# Create
@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(task_in: TaskCreate):
    # Empty/whitespace title validation
    if not task_in.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title cannot be empty."
        )

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            (task_in.title.strip(), 1 if task_in.done else 0)
        )
        conn.commit()
        created_id = cursor.lastrowid

    if created_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task."
        )

    return Task(id=created_id, title=task_in.title.strip(), done=task_in.done)

# Update
@app.patch("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def update_task(task_id: int, task_in: TaskUpdate):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if task exists
        cursor.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # Merge changes
        new_title = task_in.title.strip() if task_in.title is not None else existing["title"]
        new_done = (1 if task_in.done else 0) if task_in.done is not None else existing["done"]

        cursor.execute(
            "UPDATE tasks SET title = ?, done = ? WHERE id = ?",
            (new_title, new_done, task_id)
        )
        conn.commit()

    return Task(id=task_id, title=new_title, done=bool(new_done))

# Delete
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
async def delete_task(task_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()

    return None

# --- Optional Extra: Aggregate Statistics ---
@app.get("/stats", tags=["General"])
async def get_stats():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN done = 0 THEN 1 ELSE 0 END) AS pending
            FROM tasks
        """)
        row = cursor.fetchone()
        
        return {
            "total_tasks": row["total"],
            "completed": row["completed"] or 0,
            "pending": row["pending"] or 0
        }