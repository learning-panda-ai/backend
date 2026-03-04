from pydantic import AnyHttpUrl, BaseModel, field_validator


class IngestRequest(BaseModel):
    url: AnyHttpUrl
    replace: bool = False  # True → drop & recreate the collection; False → append

    @field_validator("url")
    @classmethod
    def must_be_pdf(cls, v: AnyHttpUrl) -> AnyHttpUrl:
        if not str(v).lower().endswith(".pdf"):
            raise ValueError("URL must point to a .pdf file")
        return v


class IngestJobResponse(BaseModel):
    task_id: str
    status: str
    status_url: str


class IngestStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None
