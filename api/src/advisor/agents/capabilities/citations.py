import re
from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.capabilities import AbstractCapability, OutputContext, ValidatedToolArgs
from pydantic_ai.messages import ToolCallPart, ToolReturn

from advisor.agents.capabilities.core import AdvisorDeps, CitationRepo, Source

MARKER = re.compile(r'\s?\[(\d+)\]')

INSTRUCTIONS = (
    'Citations: every claim derived from a web result MUST carry its marker, '
    'e.g. "[1]", using the citation ids listed under the result. Never invent ids. '
    'Claims from the portfolio tool or general knowledge take no marker.'
)


def process_citations(text: str, repo: CitationRepo) -> tuple[str, list[Source]]:
    """Strip markers with no registered source; return text plus referenced sources."""
    known = {s['id']: s for s in repo.sources()}
    referenced: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        cid = int(match.group(1))
        if cid in known:
            referenced.add(cid)
            return match.group(0)
        return ''

    cleaned = MARKER.sub(replace, text)
    return cleaned, [known[c] for c in sorted(referenced)]


@dataclass
class CitationsCapability(AbstractCapability[AdvisorDeps]):
    @classmethod
    def get_serialization_name(cls) -> str:
        return 'citations'

    def get_instructions(self) -> str:
        return INSTRUCTIONS

    async def after_tool_execute(
        self,
        ctx: RunContext[AdvisorDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        result: Any,
    ) -> Any:
        """Register web sources any tool reports and show the model their ids.

        The Exa toolset returns `ToolReturn`s whose `metadata['sources']`
        lists `{url, title}` dicts precisely so callers can wire citations.
        """
        if not isinstance(result, ToolReturn):
            return result
        sources = (result.metadata or {}).get('sources') or []
        if not sources:
            return result
        lines = []
        for source in sources:
            title = source.get('title') or source['url']
            cid = ctx.deps.citations.register(title, source['url'])
            lines.append(f'[{cid}] {title} - {source["url"]}')
        legend = 'Citation ids for these results:\n' + '\n'.join(lines)
        return replace(result, return_value=f'{result.return_value}\n\n{legend}')

    async def after_output_process(
        self, ctx: RunContext[AdvisorDeps], *, output_context: OutputContext, output: Any
    ) -> Any:
        if not isinstance(output, str):
            return output
        cleaned, referenced = process_citations(output, ctx.deps.citations)
        ctx.deps.citations.referenced = referenced
        return cleaned
