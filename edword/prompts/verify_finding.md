# Finding Verification

You are verifying an editorial finding against the original manuscript text.

## The Finding

**Type**: {finding_type}
**Severity**: {severity}
**Message**: {finding_message}

**Claim from manuscript index**:
{manuscript_claim}

**Claim from codex (ground truth)**:
{codex_claim}

## Relevant Manuscript Text

```
{manuscript_excerpt}
```

## Your Task

Carefully read the manuscript excerpt and determine:

1. **Is the manuscript claim accurate?** Does the text actually say what the index claims?
2. **Is this a real inconsistency?** Could there be context that resolves the apparent contradiction?
3. **What is the correct interpretation?**

## Output

Respond inside `<EDWORD_VERIFY>` tags with your verdict:

<EDWORD_VERIFY>
{{
  "verdict": "confirmed|dismissed|uncertain",
  "reasoning": "Explain your analysis",
  "actual_quote": "The exact text from the manuscript",
  "recommendation": "What should be done (if confirmed)"
}}
</EDWORD_VERIFY>

## Guidelines

- **confirmed**: The finding is real - there is an actual inconsistency
- **dismissed**: The finding is false - the index misread the text, or context resolves it
- **uncertain**: Cannot determine from the available text - need more context

Be precise. Quote the actual text. Explain your reasoning.
