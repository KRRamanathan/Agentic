FROM python:3.11-slim AS build

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN useradd --create-home --uid 1000 appuser
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app

COPY --from=build /opt/venv /opt/venv
COPY main.py real_llm.py structured_output.py react_loop.py tool_orchestrator.py \
     memory_agent.py hitl_approval.py cost_router.py event_automation.py \
     debate_system.py self_eval.py observability.py ./

USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
