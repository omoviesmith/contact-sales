# Agents.md

## Purpose

This document defines the AI-assisted agent layer for the Repeatable Contact Form Sales System.

It exists to make one thing explicit:

**AI enhances decisions. It does not control execution.**

The system is built around a deterministic execution core that owns queues, retries, submissions, state transitions, logging, traceability, and reliability. AI agents are invoked only at bounded points where ambiguity is high and where model output materially improves throughput or quality.

This document should be used as:

- a design reference for the agent layer
- an implementation contract between deterministic services and AI modules
- a guardrail document for future contributors
- an operations reference for logging, confidence handling, and failure modes

---

## Core Principle

The architecture is split into two layers:

### 1. Deterministic Core

Owns:

- state machine transitions
- queue orchestration
- retries and backoff
- scraper execution
- browser automation
- submission attempts
- campaign assignment
- scheduling
- logging and trace IDs
- evidence capture
- rate limiting
- final decision enforcement

### 2. AI-Assisted Intelligence Layer

Owns:

- interpretation of messy or inconsistent data
- structured extraction from unstructured content
- selective classification
- limited content generation
- fallback reasoning for edge cases
- confidence scoring

AI outputs are always treated as inputs to deterministic policy. They are never treated as direct authority over execution.

---

## System Map

Pipeline:

`Discovery -> Enrichment -> Submission -> Inbox Monitoring -> Follow-Up -> Reporting`

Each lead must carry:

- `trace_id`
- `lead_id`
- `campaign_id`
- `state`
- `status_reason`
- `audit_log`
- `confidence_summary`
- `last_agent_decision`
- `last_inbox_check_at`
- `reply_classification`
- `follow_up_eligibility`

Recommended lead states:

- `discovered`
- `enrichment_pending`
- `enriched`
- `enrichment_failed`
- `submission_pending`
- `submitting`
- `submitted`
- `submission_failed`
- `reply_pending_review`
- `replied_auto`
- `replied_human`
- `follow_up_pending`
- `follow_up_active`
- `follow_up_blocked`
- `suppressed`
- `completed`
- `dead_letter`

---

## Agent Catalog

The system should use a small set of specialized agents rather than a single general-purpose agent. Each agent must have a narrow contract, typed I/O, and explicit invocation rules.

### Agent 1: Scraper Config Generator

**Type:** Offline setup agent  
**Phase:** Discovery onboarding  
**Runtime criticality:** None  
**Execution authority:** None

#### Mission

Generate scraper configuration drafts for new lead directories so discovery can remain deterministic at runtime.

#### When It Runs

Only during scraper onboarding, regeneration, or repair. It must not run during normal production scraping.

#### Inputs

- target directory URL
- sample listing pages
- sample detail pages
- desired output schema
- extraction goals

#### Outputs

A versioned JSON scraper config that may include:

- listing selectors
- detail page selectors
- pagination rules
- field mappings
- normalization hints
- candidate contact page logic
- anti-pattern warnings

#### Guardrails

- output must be reviewed by a human before activation
- output must be schema-validated before storage
- output must be versioned in the scraper registry
- no runtime self-modification of scraper configs

#### Deterministic Owner

Discovery engine and scraper registry.

#### Failure Handling

- invalid config -> reject and request regeneration
- partial config -> store as draft only
- low-confidence selectors -> mark for manual review

#### Metrics

- time to onboard new directory
- scraper success rate by version
- selector breakage frequency
- recovery time after scraper failure

---

### Agent 2: Enrichment Extraction Agent

**Type:** Online AI agent  
**Phase:** Enrichment  
**Runtime criticality:** High  
**Execution authority:** Advisory only

#### Mission

Convert unstructured website and search data into structured lead fields usable by campaign logic and submission systems.

#### Typical Inputs

- homepage text
- about page text
- service page text
- contact page text
- metadata from directory listings
- Serper.dev results
- campaign context

#### Core Tasks

- infer founder or contact name
- infer niche or vertical
- classify services
- summarize relevance to campaign
- detect likely pain points
- detect do-not-contact signals
- produce short personalized context
- score extraction confidence

#### Example Output Fields

These should remain campaign-specific, but common fields may include:

- `founder_name`
- `company_niche`
- `service_categories`
- `partner_client`
- `client_issues`
- `total_num_issues`
- `personalization_context`
- `do_not_contact_signal`
- `submission_status_recommendation`
- `field_confidence`

#### Guardrails

- all generated fields must include confidence scores
- unsupported claims must not be fabricated
- if data is weak, fields should be omitted rather than guessed
- do-not-contact detection should bias toward caution
- generated structured data must pass schema validation

#### Deterministic Owner

Enrichment pipeline.

#### Deterministic Post-Processing

The deterministic layer should:

- validate schema
- discard low-confidence fields
- merge with known data sources
- compute final lead score
- attach campaign routing

#### Confidence Policy

- `0.85 - 1.00`: safe for direct use
- `0.60 - 0.84`: usable with fallback phrasing or soft reference
- `< 0.60`: omit from personalized messaging and submission logic

#### Failure Handling

- model timeout -> retry with lower-cost fallback model or simplified prompt
- invalid JSON -> reject and re-run with repair prompt
- low-confidence output -> persist but downgrade usage
- contradiction across sources -> flag ambiguity and restrict personalization

#### Metrics

- enrichment completion rate
- structured field acceptance rate
- low-confidence rate by field
- false personalization incidents
- average model cost per enriched lead

---

### Agent 3: DNC and Compliance Classifier

**Type:** Online AI classifier  
**Phase:** Enrichment  
**Runtime criticality:** High  
**Execution authority:** Advisory, with deterministic suppression rules

#### Mission

Identify signals that a lead should not be contacted or should be handled cautiously.

#### Signals to Detect

- explicit no-solicitation language
- support-only routing
- careers-only forms
- legal or compliance restrictions
- existing customer-only contact channels
- regional restrictions if policy applies

#### Inputs

- footer text
- contact page copy
- legal pages
- terms pages
- detected form labels
- campaign policy

#### Outputs

- `dnc_recommended: boolean`
- `dnc_reason_codes: string[]`
- `confidence`
- `review_required: boolean`

#### Guardrails

- bias toward suppression on ambiguous negative signals
- reason codes must be normalized
- suppression decisions must be explainable in logs

#### Deterministic Owner

Suppression engine.

#### Metrics

- suppression precision
- false positive suppression rate
- policy escalation rate

---

### Agent 4: Lead Prioritization Agent

**Type:** Online scoring agent  
**Phase:** Enrichment / Scale optimization  
**Runtime criticality:** Medium  
**Execution authority:** Advisory only

#### Mission

Rank leads so the system spends browser and submission capacity on the highest-value targets first.

#### Inputs

- enriched lead fields
- campaign fit score
- confidence summary
- domain quality indicators
- historical submission success
- message quality indicators

#### Outputs

- `lead_priority_score`
- `priority_reasons`
- `submission_recommendation_tier`

#### Guardrails

- must not suppress leads by itself
- must not reorder leads beyond configured campaign constraints
- deterministic queues decide final scheduling policy

#### Deterministic Owner

Queue scheduler and campaign pacing logic.

#### Metrics

- submission success by priority tier
- conversion by priority tier
- queue utilization efficiency

---

### Agent 5: Form Interpretation Agent

**Type:** Online fallback agent  
**Phase:** Submission  
**Runtime criticality:** Medium  
**Execution authority:** None

#### Mission

Interpret unknown or low-confidence forms when deterministic field-mapping logic cannot safely classify the form or individual fields.

#### Invocation Rule

This agent is called only when:

- form structure is not recognized
- CMS pattern library has no match
- field mapping confidence is below threshold
- required-vs-optional logic is uncertain
- form intent is ambiguous

#### Inputs

- DOM snapshot
- extracted labels
- placeholders
- aria attributes
- nearby text
- page title
- form action URL
- campaign field requirements

#### Outputs

- form type classification:
  - `contact_form`
  - `quote_form`
  - `support_form`
  - `job_application`
  - `newsletter`
  - `unknown`
- interpreted field map
- required field guesses
- skip recommendation
- confidence

#### Guardrails

- never submits the form directly
- never chooses retry policy
- never bypasses deterministic suppression logic
- low-confidence interpretations should cause skip or manual review, not force-fill

#### Deterministic Owner

Submission worker and form mapping engine.

#### Related Deterministic Asset

Form Pattern Library should contain:

- known field mappings by CMS
- common labels and aliases
- hidden-field handling rules
- honeypot heuristics
- domain-specific exceptions

#### Metrics

- AI fallback invocation rate
- success rate after AI-assisted mapping
- skip rate from ambiguity
- bad submission incident rate

---

### Agent 6: Message Personalization Agent

**Type:** Online content generation agent  
**Phase:** Messaging / Submission  
**Runtime criticality:** High  
**Execution authority:** Advisory only

#### Mission

Generate concise, campaign-safe, personalized contact form copy that fits predefined templates and uses enrichment data responsibly.

#### Inputs

- campaign template
- lead structured fields
- allowed personalization tokens
- tone constraints
- max length limits
- prohibited claims and wording

#### Outputs

- personalized opening line
- company/context-aware hook
- short outreach message
- fallback safe variant
- confidence score

#### Guardrails

- must operate inside deterministic templates
- must obey max character budgets
- must avoid unverifiable claims
- must degrade gracefully when personalization data is weak
- must not mention low-confidence fields directly
- must not create manipulative, deceptive, or risky phrasing

#### Deterministic Owner

Message template engine and campaign rule engine.

#### Safe Degradation Strategy

If high-confidence personalization is unavailable:

- use industry-level wording
- use offer-based messaging instead of personalized claims
- use neutral value framing
- prefer shorter copy over speculative copy

#### Metrics

- generated message acceptance rate
- submission completion rate by message variant
- reply rate by message variant
- complaint or negative signal rate
- token usage and model cost

---

### Agent 7: Reply Classification Agent

**Type:** Online AI classifier  
**Phase:** Inbox Monitoring / Follow-Up gating  
**Runtime criticality:** High  
**Execution authority:** Advisory only

#### Mission

Classify inbound messages from the Neo Space inbox so the deterministic system can tell the difference between automated form acknowledgements and real human lead replies before triggering follow-up.

#### Why This Exists

Contact-form outreach often generates auto-responses such as:

- "Thanks for contacting us"
- ticket creation confirmations
- support queue acknowledgements
- out-of-office notices
- generic mailbox automation

Those should not be treated the same as a real reply from a prospect or operator. The system needs a bounded classifier so follow-up logic can exclude leads with genuine engagement while allowing automation-only leads to continue through the sequence if policy allows.

#### When It Runs

- after a new inbound message is synced from the Neo Space inbox
- before any follow-up step is executed
- when a previous auto-reply classification is ambiguous and a new reply arrives

#### Inputs

- inbox provider: Neo Space
- message subject
- message body text
- quoted thread text when available
- sender name
- sender address
- recipient mailbox
- thread metadata
- prior outbound messages
- campaign context

#### Outputs

- `reply_type`
- `reply_subtype`
- `exclude_from_followup`
- `confidence`
- `reason_codes`
- `requires_review`

#### Suggested `reply_type` Values

- `human_reply`
- `automated_reply`
- `out_of_office`
- `bounce_or_delivery_issue`
- `unknown`

#### Suggested `reply_subtype` Values

- `positive_interest`
- `neutral_human_response`
- `rejection`
- `support_redirect`
- `form_acknowledgement`
- `ticket_created`
- `mailbox_auto_responder`
- `vacation_responder`
- `delivery_failure`

#### Guardrails

- the agent classifies only; it does not advance sequence state directly
- ambiguous replies should bias toward blocking follow-up until reviewed
- classification must consider thread history, not only the latest message
- bounces and delivery issues should be routed to deterministic suppression logic
- all classifications must be stored with confidence and reason codes

#### Deterministic Owner

Inbox monitoring service and follow-up eligibility engine.

#### Deterministic Post-Processing

The deterministic layer should:

- update lead reply state
- mark `exclude_from_followup` when human engagement is detected
- suppress or stop future follow-up on rejection or delivery failure
- allow follow-up to continue only when the latest inbox status remains automation-only or no reply

#### Metrics

- human-reply detection precision
- auto-reply detection precision
- false follow-up after human reply
- manual review rate
- time from inbox receipt to lead state update

---

### Agent 8: Follow-Up Variant Agent

**Type:** Optional content generation agent  
**Phase:** Follow-Up  
**Runtime criticality:** Low  
**Execution authority:** None

#### Mission

Generate follow-up content variants while leaving timing, sequencing, and stop logic entirely deterministic.

#### Inputs

- campaign sequence step
- prior message variant
- lead context
- tone rules
- sequence constraints

#### Outputs

- step-specific follow-up body
- alternate wording variants
- CTA variants

#### Guardrails

- no control over send timing
- no control over sequence advancement
- no override of suppression or stop conditions
- must maintain campaign tone consistency

#### Deterministic Owner

BullMQ scheduling layer and follow-up rules engine.

#### Metrics

- reply rate by follow-up variant
- stop-condition compliance
- variant fatigue indicators

---

### Agent 9: Performance Optimization Agent

**Type:** Optional analytics agent  
**Phase:** Scale and optimization  
**Runtime criticality:** Low  
**Execution authority:** None

#### Mission

Analyze historical outcomes and suggest optimizations for lead prioritization, message selection, and fallback thresholds.

#### Inputs

- submission outcomes
- enrichment confidence trends
- campaign metrics
- form-type success patterns
- message performance

#### Outputs

- recommended threshold adjustments
- campaign-specific optimization suggestions
- message variant performance insights
- lead scoring refinements

#### Guardrails

- no direct production changes
- recommendations require deterministic config changes or review
- changes should be versioned and attributable

#### Deterministic Owner

Operations workflow and configuration management.

---

## Deterministic Services That Surround the Agents

The following are not AI agents and must remain deterministic:

### Discovery Engine

- executes JSON scraper configs
- crawls listing and detail pages
- handles pagination
- normalizes source data
- deduplicates leads
- tags campaigns
- emits leads into enrichment queue

### Enrichment Pipeline

- fetches website content
- queries Serper.dev
- merges raw source data
- invokes AI agents where configured
- validates structured output
- stores confidence-aware fields

### Submission Engine

- runs Playwright workers
- detects forms
- performs field mapping
- handles captchas/proxies
- enforces per-domain pacing
- performs retries and backoff
- records evidence
- classifies outcomes

### Inbox Monitoring Engine

- reads inbound replies from the Neo Space inbox on a schedule or webhook
- maps inbox threads back to `lead_id`, `campaign_id`, and `trace_id`
- persists normalized thread data
- invokes reply classification when a new message is detected
- updates lead reply status before follow-up eligibility is evaluated
- stores message evidence and classification history

### Follow-Up Engine

- schedules delayed jobs in BullMQ
- manages sequences
- checks Neo Space inbox state before each scheduled follow-up step
- enforces stop conditions
- applies suppression rules
- excludes leads with human replies or unresolved reply ambiguity

### Reporting and Observability Layer

- stores audit logs
- attaches trace IDs across the pipeline
- records agent prompts and outputs
- calculates success and failure metrics

---

## Shared Contracts for All Agents

Every agent should use the same base invocation envelope.

### Request Contract

```json
{
  "trace_id": "uuid",
  "lead_id": "uuid",
  "campaign_id": "uuid",
  "agent_name": "message_personalization",
  "agent_version": "v1",
  "prompt_version": "2026-03-20.1",
  "input": {},
  "policy": {
    "max_tokens": 1200,
    "timeout_ms": 15000,
    "temperature": 0.2
  }
}
```

### Response Contract

```json
{
  "trace_id": "uuid",
  "lead_id": "uuid",
  "agent_name": "message_personalization",
  "agent_version": "v1",
  "output": {},
  "confidence": 0.91,
  "usage_decision": "used",
  "warnings": [],
  "model": {
    "provider": "openai",
    "name": "gpt-x",
    "latency_ms": 1820,
    "input_tokens": 940,
    "output_tokens": 210,
    "cost_usd": 0.0124
  }
}
```

### Allowed Usage Decisions

- `used`
- `ignored`
- `fallback_used`
- `requires_review`

---

## AI Logging and Transparency Requirements

Every AI interaction must be logged in a structured table or document record.

Minimum fields:

- `trace_id`
- `lead_id`
- `campaign_id`
- `agent_name`
- `agent_version`
- `prompt_version`
- `input_payload_hash`
- `raw_input_snapshot`
- `raw_output_snapshot`
- `parsed_output`
- `confidence`
- `usage_decision`
- `fallback_reason`
- `latency_ms`
- `token_usage`
- `estimated_cost`
- `created_at`

### Why This Is Mandatory

- auditability
- debugging
- reproducibility
- quality control
- cost tracking
- prompt tuning

### Additional Recommendation

Store large raw payloads in object storage and keep the database record as an indexed metadata layer with references.

---

## Confidence Handling Policy

Confidence must be explicit, normalized, and consistently used.

### Rules

- every AI-generated field should have field-level confidence when practical
- message generation should only use fields above policy threshold
- low-confidence data should never be silently promoted to truth
- confidence thresholds must be configuration-driven and campaign-aware

### Suggested Bands

- `High`: `>= 0.85`
- `Medium`: `0.60 - 0.84`
- `Low`: `< 0.60`

### Usage Policy

- high confidence -> safe for direct deterministic consumption
- medium confidence -> safe for softened phrasing or supporting signals
- low confidence -> store only, do not use in personalization or autonomous submission decisions

---

## Failure and Fallback Model

The deterministic system must assume AI can fail at any stage.

### Approved Fallback Behavior

#### Discovery

- if scraper config generation fails, keep source offline until reviewed

#### Enrichment

- fall back to deterministic fields only
- omit personalization-dependent fields
- keep lead eligible if minimum schema is satisfied

#### Submission

- if form interpretation is inconclusive, skip or park lead
- do not attempt speculative submissions

#### Messaging

- fall back to safe campaign default template
- do not block submission solely because personalization failed

#### Follow-Up

- use prewritten deterministic sequence content
- if Neo Space inbox status is stale, re-check inbox before sending
- if reply classification is ambiguous, block or park follow-up instead of sending speculatively

### Dead-Letter Conditions

Move lead or job to dead letter when:

- repeated deterministic failures exceed limit
- AI output repeatedly violates schema
- domain consistently blocks automation
- suppression ambiguity cannot be resolved safely

---

## Recommended Registry Design

### Scraper Registry

Track:

- `scraper_id`
- `source_name`
- `version`
- `config`
- `success_rate`
- `last_validated_at`
- `failure_reason`
- `status`

### Form Pattern Library

Track:

- CMS/vendor
- known selectors
- field aliases
- success rate
- anti-bot behaviors
- hidden field patterns

### Prompt Registry

Track:

- `agent_name`
- `prompt_version`
- prompt template
- expected schema
- rollout date
- experiment label
- performance notes

### Message Template Registry

Track:

- campaign type
- tone rules
- character constraints
- allowed claims
- banned phrasing
- active variants

---

## Phase-by-Phase Agent Rollout

### Phase 1: Core Infrastructure

No AI agents in production.

Build:

- PostgreSQL schema
- queue system
- lead and campaign models
- trace IDs
- structured logging
- worker foundation

### Phase 2: Discovery Engine

Introduce only the offline `Scraper Config Generator`.

Build:

- scraper execution engine
- JSON config schema
- deduplication
- normalization
- scraper registry

### Phase 3: Enrichment System

Introduce:

- `Enrichment Extraction Agent`
- `DNC and Compliance Classifier`
- optional `Lead Prioritization Agent`

Build:

- website fetcher
- Serper.dev integration
- schema validation
- confidence storage
- lead scoring

### Phase 4: Submission Engine

Introduce:

- `Form Interpretation Agent` as fallback only

Build:

- Playwright workers
- field mapping engine
- retries
- outcome classification
- screenshots and DOM evidence
- form pattern library

### Phase 5: Messaging System

Introduce:

- `Message Personalization Agent`

Build:

- template engine
- campaign rules
- safe fallback copy
- A/B variant support

### Phase 6: Follow-Up System

Introduce:

- `Reply Classification Agent`

Introduce optionally:

- `Follow-Up Variant Agent`

Build:

- delayed job scheduling
- Neo Space inbox sync and thread reconciliation
- reply-state updates on leads
- follow-up eligibility checks before each send
- sequence rules
- suppression checks
- stop conditions

### Phase 7: Scale and Optimization

Introduce optionally:

- `Performance Optimization Agent`

Build:

- concurrency tuning
- domain pacing
- dead-letter queues
- retry optimization
- optimization analytics

---

## Operational Rules

### Rule 1

No AI agent may directly mutate lead state. Only deterministic services may transition state.

### Rule 2

No AI agent may directly trigger a submission attempt. Submission workers alone own browser actions.

### Rule 3

No AI agent may decide retry count, backoff strategy, queue priority, or suppression bypass.

### Rule 4

All AI outputs must be schema-validated before use.

### Rule 5

All AI usage must be attributable by prompt version, model version, and agent version.

### Rule 6

Any AI-generated personalization must gracefully degrade to non-personalized safe messaging.

### Rule 7

Compliance and suppression logic must prefer false negatives in outreach volume over false positives in risky outreach.

### Rule 8

No follow-up step may be sent until the deterministic system has checked the latest Neo Space inbox state for that lead or thread.

### Rule 9

The reply-classification agent may recommend excluding a lead from follow-up, but only deterministic follow-up eligibility logic may enforce that exclusion by changing lead state.

---

## Suggested Initial File/Module Layout

```text
src/
  discovery/
    scraper-engine/
    scraper-registry/
    scraper-config-schema/
  enrichment/
    fetchers/
    parsers/
    agents/
      enrichment-extraction.agent.ts
      dnc-classifier.agent.ts
      lead-prioritization.agent.ts
    schemas/
  submission/
    playwright/
    form-mapper/
    pattern-library/
    agents/
      form-interpretation.agent.ts
  inbox/
    neo-space-sync/
    thread-mapper/
    agents/
      reply-classification.agent.ts
  messaging/
    templates/
    agents/
      message-personalization.agent.ts
      follow-up-variant.agent.ts
  optimization/
    agents/
      performance-optimization.agent.ts
  shared/
    tracing/
    logging/
    llm/
    contracts/
    confidence/
```

---

## Success Criteria for the Agent Layer

The agent layer is successful when it improves system quality without weakening deterministic control.

Measure success by:

- 1,000+ submissions per day supported by stable workers
- improved enrichment quality over deterministic parsing alone
- improved personalization quality without hallucination-driven errors
- low AI invocation rate in runtime-critical submission paths
- full auditability for every AI-assisted decision
- predictable operation under concurrency and failure

---

## Final Design Position

This system should not be built as an autonomous swarm of agents.

It should be built as a deterministic pipeline with a narrow, accountable agent layer that:

- resolves ambiguity
- generates structured outputs
- improves message quality
- helps with edge cases

The deterministic core remains the product. The agents are support systems attached to it.

That distinction is what makes the system scalable, debuggable, and safe to run at volume.
