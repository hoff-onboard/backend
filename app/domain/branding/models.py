from pydantic import BaseModel


class Brand(BaseModel):
    primary: str
    secondary: str = ""
    background: str
    text: str
    fontFamily: str
    borderRadius: str
