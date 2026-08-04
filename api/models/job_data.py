from pydantic import BaseModel


class JobData(BaseModel):
    name: str
    job_type: str
    user_email: str = "developers@inuits.eu"
    track_async_children: bool = False
    parent_id: str | None = None
