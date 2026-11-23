import { Headphones, Pause, Play } from "lucide-react";
import { usePlayer, type Track } from "../audio/player";
import { useApp } from "../settings";

interface Props {
  tracks: () => Track[];
  trackKey: string;
  label?: string;
  variant?: "icon" | "pill";
}

export function ListenButton({ tracks, trackKey, label, variant = "pill" }: Props) {
  const { t } = useApp();
  const player = usePlayer();
  const active = player.isCurrent(trackKey);
  const playing = active && (player.status === "playing" || player.status === "loading");

  const onClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (active) player.toggle();
    else player.play(tracks());
  };
  const text = playing ? t.pause : label ?? t.listen;
  if (variant === "icon") {
    return (
      <button className={`icon-btn listen-icon${active ? " active" : ""}`} onClick={onClick} aria-label={text} title={text}>
        {playing ? <Pause size={16} /> : <Headphones size={16} />}
      </button>
    );
  }
  return (
    <button className={`pill-btn${active ? " active" : ""}`} onClick={onClick}>
      {playing ? <Pause size={16} /> : <Play size={16} />}
      <span>{text}</span>
    </button>
  );
}
