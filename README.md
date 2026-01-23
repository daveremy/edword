# Edword

AI-powered editorial analysis for book manuscripts.

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Show project info
edword info

# Run analysis
edword analyze

# Run specific pass
edword analyze continuity

# Save report
edword analyze --save
```

## Configuration

Create `edword.yaml` in your project root:

```yaml
project:
  name: "My Novel"

paths:
  manuscripts: "manuscripts/"
  codex: "codex/"

llm:
  provider: "claude"
  model: "opus"
```
