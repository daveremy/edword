# Verification Questions

You are verifying an editorial finding from a manuscript analysis tool.
Generate 3-5 questions that would help determine if this finding is real or a false positive.

## The Finding
**Message**: {finding_message}
**Location**: {finding_location}

## Evidence from Manuscript
```
{evidence}
```

## Output
Generate questions in <EDWORD_QUESTIONS> tags as a JSON array:

<EDWORD_QUESTIONS>
["Question 1?", "Question 2?", "Question 3?"]
</EDWORD_QUESTIONS>

## Guidelines

Questions should probe:
- Is the quoted text or claim in the finding accurate?
- Is there context being missed that would explain the apparent inconsistency?
- Could both claims be true in different circumstances or timeframes?
- Are there aliases, nicknames, or different references to the same entity?
- Is there narrative unreliability (character misremembering, lying, etc.)?

Generate 3-5 specific, answerable questions based on the finding and evidence.
