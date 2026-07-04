from pydantic import BaseModel


class PingResponseSchema(BaseModel):
    message: str
    count: int
