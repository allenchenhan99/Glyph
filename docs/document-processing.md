# Document processing

Document processing runs as a local background job. The browser displays durable job state; closing or refreshing the page does not cancel work.

## Before processing

Glyph checks the source file, extraction/OCR configuration, and selected translation provider before enqueueing. These checks make no model request. A configured API key or installed CLI does not prove authentication, account balance, model access, or translation quality; a provider can still reject a later request.

Text extraction requires Poppler for PDF input. Scanned PDFs and images need a configured OCR adapter. Glyph must not produce invented OCR text when extraction is unavailable. Preflight errors identify the missing requirement and preserve the document for a later retry.

## Progress and cancellation

Process returns a queued job promptly. The workspace recovers the latest job for each document, shows its stage and any known block counts, and polls while work remains active. Existing Reader, Research Map and Implementation Contract views remain available.

Cancel requests cooperative cancellation. A queued job can stop immediately; an already-running external OCR/model call may finish before Glyph reaches the next cancellation boundary. Cancellation does not reverse a provider charge for a request already sent. Successful validated translation batches remain cached for a later retry.

## Failure, restart and retry

Failed, cancelled and interrupted jobs retain their last readable document snapshot. A successful run replaces the Reader atomically only if the source still matches that run. A source that changes during processing must be retried against its current contents.

On backend restart, unfinished jobs are marked interrupted. They are not automatically replayed: their original session credentials may no longer exist. Use Retry processing after checking the current provider settings. Retry creates a new job and reuses compatible cached translation batches.

Keys entered in Translation settings are held only in backend memory. Job records may contain provider/model names and progress, but never the key. Research Map and Implementation Contract providers keep their separate existing configuration.

## API

- `GET /api/documents/{id}/preflight`: read-only readiness report with actionable issues.
- `POST /api/documents/{id}/process`: enqueue and return a job with HTTP 202; active work for the same document is a conflict.
- `GET /api/jobs`: latest processing job per document.
- `GET /api/jobs/{id}`: current progress and result.
- `POST /api/jobs/{id}/cancel`: request cancellation and return updated state.

Job states are `queued`, `running`, `completed`, `failed`, `cancelled`, and `interrupted`. Progress/block counts are observations, not an estimated completion time. External calls remain subject to their configured timeouts.
