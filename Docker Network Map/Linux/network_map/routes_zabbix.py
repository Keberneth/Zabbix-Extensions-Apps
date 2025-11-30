from fastapi import APIRouter

from state import add_problem, remove_problem, get_active_problems

router = APIRouter()


@router.post("/api/webhook/zabbix_event")
async def zabbix_event(payload: dict):
    event_type = payload.get("event")
    server = payload.get("server")
    if not event_type or not server:
        return {"status": "ignored"}

    et = str(event_type).lower()
    server_str = str(server)

    if et == "problem":
        add_problem(server_str)
    elif et == "resolve":
        remove_problem(server_str)

    return {"status": "ok"}


@router.get("/api/problems")
def get_problems():
    return {"problems": get_active_problems()}
