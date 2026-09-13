# Reliable document processing design

The user approved the proposed preflight and background-processing phase. Keep Glyph a local single-user application: use its existing SQLAlchemy database and an in-process worker with durable job records. A browser-only progress spinner cannot survive navigation; a separate Redis/Celery service adds deployment requirements that this application does not need.

Capture provider/model and credentials in memory when enqueueing; persist only safe metadata. Return 202 after committing the queued job, run OCR/translation outside a long-lived write transaction, and commit stage/block progress independently. Publish the Reader atomically only after verifying source identity and cancellation state. Enforce active-job uniqueness in the database. On restart, mark queued/running jobs interrupted with a retry action rather than silently resubmitting paid work without the original session credentials.

Preflight is read-only and has bounded subprocess timeouts. Missing source, unavailable CLI, missing OrcaRouter model/key, and image/scanned input without OCR are explicit blockers. Preflight checks local configuration only, not account authentication/balance. Development fixtures must not cause real scanned files to receive fabricated OCR text.

API contract:
- GET /api/documents/{id}/preflight -> {ready: boolean, source_type: string, provider: string, page_count: number|null, issues: [{code: string, severity: error|warning, message: string}]}.
- POST /api/documents/{id}/process -> 202 ProcessingJob; blockers -> actionable 422 detail, active work -> 409.
- GET /api/jobs -> latest job per document (including terminal jobs), bounded history; GET /api/jobs/{id} -> ProcessingJob.
- POST /api/jobs/{id}/cancel -> ProcessingJob; queued work cancels immediately, running work requests cooperative cancellation.
- ProcessingJob keeps existing fields and adds optional/nullable completed_blocks, total_blocks, cancel_requested, provider, model. Statuses: queued, running, completed, failed, cancelled, interrupted. Retry creates a new job with current settings and reuses validated cache.

Frontend obtains preflight before submission, presents errors/warnings, tracks jobs separately from Reader/Map selection, polls while jobs are active, and restores status on reload. Cancellation messaging explains in-flight call behavior. Existing Reader/Map/Contract remains usable while work runs.
