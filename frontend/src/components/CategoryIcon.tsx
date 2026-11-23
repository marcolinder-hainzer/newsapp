import { Cpu, FlaskConical, Globe, HeartPulse, Landmark, Layers, Leaf, Newspaper, Palette, TrendingUp, Trophy } from "lucide-react";
import type { LucideProps } from "lucide-react";

const ICONS: Record<string, React.ComponentType<LucideProps>> = {
  landmark: Landmark,
  globe: Globe,
  "trending-up": TrendingUp,
  cpu: Cpu,
  flask: FlaskConical,
  "heart-pulse": HeartPulse,
  leaf: Leaf,
  trophy: Trophy,
  palette: Palette,
  newspaper: Newspaper,
};

export function CategoryIcon({ icon, size = 16 }: { icon?: string; size?: number }) {
  const Icon = (icon && ICONS[icon]) || Layers;
  return <Icon size={size} aria-hidden="true" />;
}
