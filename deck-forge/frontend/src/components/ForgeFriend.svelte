<script>
  import { agentBusy, agentReply, agentThinking, agentAttached } from "../lib/store.js";
  import { askForge } from "../lib/agent.js";
  import ReplyText from "./ReplyText.svelte";

  const KIND_LABEL = {
    next_move: "Next move",
    explain: "Explanation",
    novel_synergies: "Novel synergies",
  };

  // Session-attach status is polled once, centrally, in App.svelte and shared via the
  // store (the footer's ● Session dot reads the same source).
  $: attached = $agentAttached;
</script>

<div class="panel widget friend">
  <h3 class="panel-title">
    Forge-Friend
    <span class="sess" class:on={attached}>{attached ? "● attached" : "○ no session"}</span>
  </h3>

  <button class="btn btn-ember nudge" on:click={() => askForge("next_move")} disabled={$agentBusy}>
    {$agentBusy ? ($agentThinking ? "Reasoning…" : "Thinking…") : "✦ Suggest next move"}
  </button>

  {#if $agentReply}
    <div class="reply" class:offline={$agentReply.offline}>
      <div class="kind">{KIND_LABEL[$agentReply.kind] || $agentReply.kind}</div>
      {#if $agentReply.offline}
        <p class="text">{$agentReply.text}</p>
      {:else}
        <ReplyText text={$agentReply.text} cards={$agentReply.cards || []} />
      {/if}
    </div>
  {:else if $agentBusy}
    <p class="hint ok">
      {$agentThinking
        ? "Forge-friend is reasoning — grounded answers (real card-search + oracle checks) can take a minute…"
        : "Asking the forge-friend…"}
    </p>
  {:else if attached}
    <p class="hint ok">Forge-friend is here. Ask for the next move, or hit <span class="q">?</span> on any card.</p>
  {:else}
    <p class="hint">
      No session attached. Run <code>/deck-forge</code> in an interactive Claude Code
      session for novel synergies, rules answers, and guidance.
    </p>
  {/if}
</div>

<style>
  .sess {
    text-transform: none;
    letter-spacing: 0;
    font-family: var(--body);
    font-size: 0.66rem;
    color: var(--muted);
  }
  .sess.on {
    color: var(--pass);
  }
  .nudge {
    width: 100%;
    font-family: var(--display);
    letter-spacing: 0.08em;
  }
  .reply {
    margin-top: 0.7rem;
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--ember);
    border-radius: var(--radius);
    padding: 0.6rem 0.7rem;
    background: rgba(255, 106, 61, 0.06);
    animation: rise 0.25s ease both;
  }
  .reply.offline {
    border-left-color: var(--muted);
    background: rgba(0, 0, 0, 0.2);
  }
  .kind {
    font-family: var(--display);
    font-size: 0.68rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--brass);
    margin-bottom: 0.3rem;
  }
  .text {
    margin: 0;
    font-size: 0.86rem;
    line-height: 1.45;
    white-space: pre-wrap;
  }
  .hint {
    margin: 0.6rem 0 0;
    font-size: 0.74rem;
    font-style: italic;
    color: var(--muted);
  }
  .hint.ok {
    color: var(--parchment-dim);
    font-style: normal;
  }
  .hint code,
  .hint .q {
    color: var(--brass);
    font-style: normal;
  }
</style>
