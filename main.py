from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="Task API", version="1.0.0")

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

# --- In-Momory Storage (0(1)) lookups) ---
tasks_db: Dict[int, Task] = {
    1: Task(id=1, title="Buy groceries", done=False),
    2: Task(id=2, title="Walk the dog", done=True),
    3: Task(id=3, title="Clean my room", done=False)
}

next_id: int = max(tasks_db.keys(), default=0) + 1

# --- Endpoints ---
@app.get("/", tags=["General"])
async def root():
    return {
        "name": 'Task API',
        "version": "1.0",
        "endpoints": ["/tasks", "/health"]
    }

@app.get("/health", tags=["General"])
async def health():
    return {"status": "ok"}

# Read all tasks
@app.get("/tasks", response_model=List[Task], tags=["Tasks"])
async def get_tasks():
    return list(tasks_db.values())

# Read one task
@app.get("/tasks/{task_id}", response_model=List[Task], tags=["Tasks"])
async def get_task(task_id: int):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tas with ID {task_id} not found."
        )
    return task

# Create
@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(task_in: TaskCreate):
    global next_id
    new_task = Task(id=next_id, **task_in.model_dump())
    tasks_db[next_id] = new_task
    next_id += 1
    return new_task

# Update
@app.patch("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def update_task(task_id: int, task_in: TaskUpdate):
    stored_task = tasks_db.get(task_id)
    if not stored_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found."
        )

    # Update only provided fields
    update_data = task_in.model_dump(exclude_unset=True)
    updated_task = stored_task.model_copy(update=update_data)
    tasks_db[task_id] = updated_task
    return updated_task

# Delete
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
async def delete_task(task_id: int):
    if task_id not in tasks_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found"
        )
    del tasks_db[task_id]
    return None