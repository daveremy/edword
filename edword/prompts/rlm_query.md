# Ad-Hoc Query

You are analyzing a manuscript to answer a specific question.

## Question

{query}

## Context

{context_description}

The document is available in the `context` variable ({context_size:,} characters).

## Instructions

Write Python code to explore the document and find the answer. You have access to:

- `context` (str): The full document text
- `re`: Python regex module (already imported)
- `print()`, `len()`, `str()`, `int()`, `list()`, `dict()`, `range()`, `enumerate()`, `zip()`, `sorted()`, `min()`, `max()`, `sum()`

DO NOT use import statements - everything you need is already available.

## Example

```python
# Find all mentions of a character
mentions = re.findall(r'Greg\s+Walsh|Dr\.\s*Walsh|Greg', context)
print(f"Found {{len(mentions)}} mentions")
print(context[0:500])  # See beginning for context
```

When you have your answer, write: `FINAL("your answer here")`

Write your code now.
