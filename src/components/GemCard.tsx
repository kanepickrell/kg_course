import { SavedGem } from "./GemSaveModal";
import { Gem, Tag, Calendar, Trash2, ExternalLink, Eye, Pickaxe, Layers, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";

interface GemCardProps {
  gem: SavedGem;
  onDelete: (gemId: string) => void;
  onView: (nodeId: string) => void;
}

const GemCard: React.FC<GemCardProps> = ({ gem, onDelete, onView }) => {
  const formatDate = (date: Date) => {
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  };

  const isProspect = gem.type === "prospect";
  const Icon = isProspect ? Pickaxe : Gem;
  const iconColor = isProspect ? "text-orange-500" : "text-accent-pink";
  const borderColor = isProspect ? "border-l-orange-500" : "border-l-accent-pink";

  return (
    <div className={`neo-card p-4 hover:shadow-lg transition-shadow bg-card border-l-4 ${borderColor}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-start gap-2 flex-1">
          <Icon className={`w-4 h-4 ${iconColor} mt-0.5 flex-shrink-0`} />
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-bold truncate">{gem.label}</h4>
            <p className="text-xs text-muted-foreground">
              {isProspect ? "Prospect" : "Hidden Gem"} • {gem.cluster}
            </p>
          </div>
        </div>
        <button
          onClick={() => onDelete(gem.id)}
          className="p-1 hover:bg-destructive/10 rounded transition-colors"
          title={`Delete ${isProspect ? 'prospect' : 'gem'}`}
        >
          <Trash2 className="w-3 h-3 text-destructive" />
        </button>
      </div>

      {/* Prospect-specific metadata */}
      {isProspect && (
        <div className="mb-2 grid grid-cols-3 gap-1">
          <div className="neo-card p-1.5 bg-secondary/30 text-center">
            <div className="text-xs font-bold">{gem.nodeCount || gem.nodeIds.length}</div>
            <div className="text-[9px] text-muted-foreground">nodes</div>
          </div>
          {gem.expansionDepth && (
            <div className="neo-card p-1.5 bg-secondary/30 text-center">
              <div className="text-xs font-bold">{gem.expansionDepth}</div>
              <div className="text-[9px] text-muted-foreground">depth</div>
            </div>
          )}
          {gem.prospectType && (
            <div className="neo-card p-1.5 bg-secondary/30 text-center">
              <div className="text-[9px] font-bold capitalize truncate">{gem.prospectType}</div>
            </div>
          )}
        </div>
      )}

      {/* Tags */}
      {gem.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {gem.tags.map((tag, idx) => (
            <span
              key={idx}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-secondary border border-border rounded-full text-[10px] font-semibold"
            >
              <Tag className="w-2.5 h-2.5" />
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Notes */}
      {gem.notes && (
        <p className="text-xs text-muted-foreground mb-3 line-clamp-2 leading-relaxed">
          {gem.notes}
        </p>
      )}

      {/* Importance Indicator */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-[10px] mb-1">
          <span className="text-muted-foreground">Importance</span>
          <span className="font-mono font-bold">{Math.round(gem.importance * 100)}%</span>
        </div>
        <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
          <div
            className={`h-full ${isProspect ? 'bg-orange-500' : 'bg-accent-pink'}`}
            style={{ width: `${gem.importance * 100}%` }}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-border">
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <Calendar className="w-3 h-3" />
          {formatDate(gem.capturedAt)}
        </div>
        <Button
          onClick={() => onView(gem.nodeIds[0])}
          size="sm"
          variant="ghost"
          className="h-7 text-xs gap-1"
        >
          <Eye className="w-3 h-3" />
          {isProspect && gem.nodeIds.length > 1 ? "View Nodes" : "View in Graph"}
        </Button>
      </div>
    </div>
  );
};

export default GemCard;