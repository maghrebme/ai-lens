// Ai-Lens — start the GitHub Pages build at exact times.
//
// GitHub's own schedule starts free-tier runs hours late. Cloudflare Cron
// Triggers fire on time, so this Worker asks GitHub to run the workflow at
// 00:00 and 12:00 UTC (see wrangler.toml). It has no public URL.
//
// Secret: GITHUB_TOKEN — a fine-grained token limited to this repository,
// with "Actions: read and write" only. Set it with `wrangler secret put`.

const REPO = 'maghrebme/ai-lens';
const WORKFLOW = 'pages.yml';

export default {
  async scheduled(event, env, ctx) {
    const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'ai-lens-cron',
      },
      body: JSON.stringify({ ref: 'main' }),
    });
    // 204 means GitHub accepted the run. Anything else shows up as a failed
    // invocation in the Worker's logs in the Cloudflare dashboard.
    if (res.status !== 204) {
      throw new Error(`dispatch failed: ${res.status} ${(await res.text()).slice(0, 200)}`);
    }
  },
};
