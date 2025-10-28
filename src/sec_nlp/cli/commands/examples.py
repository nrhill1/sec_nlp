# sec_nlp/cli/commands/examples.py
"""Examples command to show common usage patterns."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


def examples_command() -> None:
    """Show example commands and usage patterns."""
    examples_md = """
# SEC NLP Pipeline - Examples

## Basic Usage

### Single Company Analysis
```bash
# Analyze Apple's annual filings (default: last year)
sec-nlp run AAPL

# Interactive mode with guided prompts
sec-nlp run -i
```

### Multiple Companies
```bash
# Analyze several companies at once
sec-nlp run AAPL MSFT GOOGL TSLA

# With custom date range
sec-nlp run AAPL MSFT -s 2023-01-01 -e 2024-12-31
```

## Advanced Options

### Custom Search Keywords
```bash
# Search for liquidity mentions
sec-nlp run AAPL -k liquidity

# Quarterly filings with revenue keyword
sec-nlp run AAPL -m quarterly -k revenue
```

### Different Models
```bash
# Use larger T5 model
sec-nlp run AAPL --model google/flan-t5-large

# Use local Ollama model
sec-nlp run AAPL --model ollama:llama3.2

# With custom prompt template
sec-nlp run AAPL -p ./my-prompt.yml
```

### Processing Options
```bash
# Process more filings per symbol
sec-nlp run AAPL -l 5

# Larger batch size for faster processing
sec-nlp run AAPL -b 32

# Don't clean up downloads
sec-nlp run AAPL --no-cleanup
```

## Development & Testing

### Dry Run Mode
```bash
# Test configuration without API calls
sec-nlp run AAPL --dry-run -v

# Fresh start (clear existing files)
sec-nlp run AAPL -f --dry-run
```

### Logging
```bash
# Verbose logging
sec-nlp run AAPL -v

# Save logs to file
sec-nlp run AAPL --log-file pipeline.log

# JSON formatted logs
sec-nlp run AAPL --log-format json
```

## Common Workflows

### Daily Market Analysis
```bash
# Analyze top tech stocks with liquidity focus
sec-nlp run AAPL MSFT GOOGL AMZN -k liquidity -l 1
```

### Quarterly Earnings Deep Dive
```bash
# Analyze Q4 earnings for specific companies
sec-nlp run AAPL MSFT \\
  -m quarterly \\
  -s 2024-10-01 \\
  -e 2024-12-31 \\
  -k earnings \\
  -l 2
```

### Comparative Analysis Setup
```bash
# Generate summaries for sector comparison
sec-nlp run AAPL GOOGL MSFT \\
  --model ollama:llama3.2 \\
  -k "market position" \\
  --no-cleanup
```

## Tips

- Use `-i/--interactive` for a guided experience
- Start with `--dry-run` to test configuration
- Use `--help` on any command for detailed options
- Check `--version` for current version info
    """

    md = Markdown(examples_md)
    console.print(
        Panel(md, title="[bold cyan]Examples & Usage Patterns[/bold cyan]", border_style="cyan")
    )


if __name__ == "__main__":
    examples_command()
