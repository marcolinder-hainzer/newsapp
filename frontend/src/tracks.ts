import { api } from "./api";
import type { Track } from "./audio/player";
import type { Digest, Lang, StoryItem } from "./types";

export function storyTrack(story: StoryItem, lang: Lang): Track {
  return {
    key: `story-${story.id}-${lang}`,
    title: story.title[lang],
    lang,
    href: `/meldung/${story.id}`,
    getSpeech: async () => (await api.story(story.id)).speech[lang],
  };
}

export function digestTrack(digest: Digest, lang: Lang): Track {
  return {
    key: `digest-${digest.scope}-${lang}`,
    title: digest.content[lang]?.headline || digest.title[lang],
    lang,
    href: digest.scope.startsWith("category:") ? `/kategorie/${digest.scope.split(":")[1]}` : "/briefing",
    getSpeech: async () => ({ text: digest.speech[lang], lang }),
  };
}
