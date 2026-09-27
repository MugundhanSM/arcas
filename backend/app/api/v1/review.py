from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.core.guardrails import InputGuardrails
from app.core.logging import get_logger
from app.core.rate_limit import (
    RateLimitExceeded,
    client_identity,
    rate_limiter,
)
from app.core.security import decode_access_token
from app.database.dependencies import get_db
from app.database.session import SessionLocal
from app.repositories.review_session_repository import ReviewSessionRepository
from app.schemas.request import ReviewIntent, ReviewRequest
from app.schemas.response import ReviewResponse
from app.services.review_service import ReviewService

router = APIRouter()
logger = get_logger("arcas.api.review")


def _enforce_rate_limit(request: Request) -> None:
    identity, _ = client_identity(request)
    try:
        rate_limiter.check(identity)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(exc.retry_after)},
        )


def _valid_intent(raw: str) -> str:
    try:
        return ReviewIntent(raw).value
    except ValueError:
        valid = ", ".join(e.value for e in ReviewIntent)
        raise ValueError(
            f"Invalid intent '{raw}'. Must be one of: {valid}."
        )


@router.post("/review", response_model=ReviewResponse)
async def review_code(
    request: ReviewRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    # Rate limiting - keyed by authenticated user or client IP.
    _enforce_rate_limit(http_request)

    # Input guardrails layer
    guardrail = InputGuardrails.check(
        code=request.code,
        language=request.language,
    )

    if not guardrail.allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Request blocked by input guardrails.",
                "violations": guardrail.violations,
            },
        )

    code = getattr(guardrail, "sanitized_code", None) or request.code

    review_result = await ReviewService.process_review(
        db=db,
        language=guardrail.normalized_language,
        source_code=code,
        intent=request.intent.value,
        actor=user,
        client_session_id=request.session_id,
        request_text=request.request_text or "",
    )

    return ReviewResponse(
        session_id=review_result["session_id"],
        language=guardrail.normalized_language,
        review_findings=review_result["review_findings"],
        security_findings=review_result["security_findings"],
        risk_analysis=review_result["risk_analysis"],
        metrics=review_result["metrics"],
        refactor_recommendations=(
            review_result["refactor_recommendations"]
        ),
        refactor_diff=review_result.get("refactor_diff", ""),
        refactored_code=review_result.get("refactored_code", ""),
        documentation=review_result.get("documentation", ""),
        generated_tests=review_result.get("generated_tests", ""),
        output_guardrail=review_result.get("output_guardrail", {}),
        workspace_warnings=review_result.get("workspace_warnings", []),
        react_traces=review_result.get("react_traces", {}),
        source_code=review_result.get("source_code", code),
        intent=review_result.get("intent", request.intent.value),
        intent_confidence=review_result.get("intent_confidence"),
        intent_signals=review_result.get("intent_signals", []),
        warnings=guardrail.warnings,
        message=(
            f"{guardrail.normalized_language} code analyzed successfully"
        ),
    )


class WorkspaceNameRequest(BaseModel):
    name: str


@router.patch("/review/{session_id}/name")
async def update_workspace_name(
    session_id: str,
    payload: WorkspaceNameRequest,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """Update the workspace name for a review session."""
    name = payload.name.strip()
    if not name or len(name) > 120:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name must be 1-120 characters.",
        )
    updated = ReviewSessionRepository.update_workspace_name(
        db, session_id=session_id, workspace_name=name, actor=user
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review session not found.",
        )
    return {"session_id": session_id, "workspace_name": updated.workspace_name}


@router.websocket("/review/stream")
async def review_stream(websocket: WebSocket):
    """Stream the review pipeline stage-by-stage to the client."""
    await websocket.accept()

    # Optional auth via query-string token (browsers cannot set WS headers).
    token = websocket.query_params.get("token")
    if token:
        payload = decode_access_token(token)
        websocket.state.user = payload.get("sub") if payload else None
    else:
        websocket.state.user = None

    # Enforce authentication when required.
    if settings.AUTH_REQUIRED and not websocket.state.user:
        await websocket.send_json(
            {"stage": "error", "message": "Authentication required."}
        )
        await websocket.close()
        return

    # Rate limit the socket - keyed by authenticated user or client IP.
    identity = websocket.state.user or (
        websocket.client.host if websocket.client else "anonymous"
    )
    try:
        rate_limiter.check(str(identity))
    except RateLimitExceeded as exc:
        await websocket.send_json(
            {
                "stage": "error",
                "message": "Rate limit exceeded. Please retry later.",
                "retry_after": exc.retry_after,
            }
        )
        await websocket.close()
        return

    try:
        request = await websocket.receive_json()
    except Exception:  # noqa: BLE001
        await websocket.send_json(
            {"stage": "error", "message": "Invalid request payload."}
        )
        await websocket.close()
        return

    code = request.get("code", "")
    language = request.get("language", "python")
    raw_intent = request.get("intent", "full_review")

    try:
        intent = _valid_intent(raw_intent)
    except ValueError as exc:
        await websocket.send_json(
            {"stage": "error", "message": str(exc)}
        )
        await websocket.close()
        return

    guardrail = InputGuardrails.check(code=code, language=language)
    if not guardrail.allowed:
        await websocket.send_json(
            {
                "stage": "error",
                "message": "Blocked by input guardrails.",
                "violations": guardrail.violations,
            }
        )
        await websocket.close()
        return

    try:
        await websocket.send_json(
            {
                "stage": "input_guardrails",
                "status": "running",
                "message": "Validating and sanitising input",
            }
        )
        await websocket.send_json(
            {
                "stage": "input_guardrails",
                "status": "done",
                "message": "Input validated and sanitised",
            }
        )

        # Stream the pipeline stage-by-stage.
        db = SessionLocal()
        try:
            async for event in ReviewService.process_review_streaming(
                db=db,
                language=guardrail.normalized_language,
                source_code=(
                    getattr(guardrail, "sanitized_code", None) or code
                ),
                intent=intent,
                actor=getattr(websocket.state, "user", None),
                client_session_id=request.get("session_id"),
                request_text=request.get("request_text", ""),
            ):
                if event.get("stage") == "complete":
                    event["data"].update(
                        {
                            "language": guardrail.normalized_language,
                            "warnings": guardrail.warnings,
                            "message": (
                                f"{guardrail.normalized_language} code "
                                "analyzed successfully"
                            ),
                        }
                    )
                await websocket.send_json(event)
        finally:
            db.close()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected during streaming review.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Streaming review failed: %s", exc)
        try:
            await websocket.send_json(
                {"stage": "error", "message": "Internal error during review."}
            )
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
