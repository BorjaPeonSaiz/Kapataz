# Data protection questions for Anthropic (follow-up for the sales team)

**Subject:** Zero data retention and sub-processor terms for an EU processor using the Claude API

**From:** Borja Peón, KodigoLab (Spain) · **Date:** November 2026

Hello,

Your support team answered part of our data protection questions and referred us to you for the rest. We need written answers to the three questions below before we send any real customer data to the Claude API.

## Our setup

KodigoLab is building Kapataz, an invoicing service for self-employed tradespeople in Spain. We call the Claude API (`api.anthropic.com`) from our EU servers under the Commercial Terms. We plan to launch in 2027, with a few dozen customers at first.

- **Roles under the GDPR:** each of our customers is the controller of their own clients' data. KodigoLab is their processor. Anthropic would be our sub-processor.
- **What we send:** text only, pseudonymised on our servers first. Names, tax IDs, addresses and phone numbers are replaced with tokens. We never send files, images or audio.
- **Model:** Claude Opus 5.5, through the Messages API only. We do not use the Batch API, the Files API or code execution.

## What support already confirmed

Your Data Processing Addendum covers processor-to-processor transfers through Module Three of the Standard Contractual Clauses, with no separate agreement.

## What we read in your documentation

Please correct us if any of this is wrong:

- As a customer in the EEA, we contract with Anthropic Ireland, Limited.
- Without zero data retention, API inputs and outputs are deleted within 30 days. Flagged content may be kept for up to 2 years, and classification scores for up to 7 years.
- On the Claude API, `inference_geo` accepts only `us` and `global`, and data at rest is stored in the United States, so EU-only processing is not available.

## Questions

1. **Zero data retention.** Can it be enabled for our organization? What are the conditions, and is there a minimum spend or plan?
2. **Transfers to the United States.** Your addendum names Anthropic Ireland as the data importer. When Anthropic Ireland sends our data to Anthropic, PBC, which safeguard applies? Is Anthropic, PBC certified under the EU-US Data Privacy Framework?
3. **Sub-processor changes.** Is the Trust Center news feed (`trust.anthropic.com/updates`) the formal notice under section C.3 of the addendum, or do you also notify customers by email, as a Notice under section M.1 of the Commercial Terms? We must pass the notice on to our own customers within your 15-day objection period.

## Why it matters

We must name Anthropic as a sub-processor in our customer contracts and document the transfer safeguards. Our lawyer will review your answers.

Thank you,

Borja Peón
KodigoLab
