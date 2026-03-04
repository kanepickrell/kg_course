import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Activity, Zap, Database, Shield, Server, Globe } from 'lucide-react';

const getIconForType = (type: string) => {
    switch (type?.toLowerCase()) {
        case 'automation':
            return <Zap className="w-3 h-3" />;
        case 'data':
            return <Database className="w-3 h-3" />;
        case 'security':
            return <Shield className="w-3 h-3" />;
        case 'infrastructure':
            return <Server className="w-3 h-3" />;
        case 'network':
            return <Globe className="w-3 h-3" />;
        default:
            return <Activity className="w-3 h-3" />;
    }
};

const CustomNode = ({ data, selected }: NodeProps) => {
    const importance = data.importance || 0.5;
    const isSelected = selected || data.selected;

    // Calculate size based on importance
    const size = 30 + (importance * 40); // 30-70px range

    return (
        <>
            {/* Input Handle */}
            <Handle
                type="target"
                position={Position.Top}
                style={{
                    width: 8,
                    height: 8,
                    background: data.color,
                    border: '2px solid #000',
                }}
            />

            <div
                className={`
                    neo-card px-3 py-2 cursor-pointer transition-all duration-200
                    ${isSelected ? 'ring-4 ring-accent-pink shadow-lg scale-110' : 'hover:shadow-md'}
                `}
                style={{
                    minWidth: `${size}px`,
                    backgroundColor: isSelected ? `${data.color}20` : '#fff',
                    borderColor: data.color,
                    borderLeftWidth: '4px',
                }}
            >
                {/* Header with icon and label */}
                <div className="flex items-center gap-2">
                    <div
                        className="flex-shrink-0 p-1 rounded"
                        style={{
                            backgroundColor: `${data.color}30`,
                            color: data.color,
                        }}
                    >
                        {getIconForType(data.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold truncate leading-tight">
                            {data.label}
                        </div>
                        <div className="text-[10px] text-muted-foreground truncate">
                            {data.cluster}
                        </div>
                    </div>
                </div>

                {/* Importance indicator */}
                {importance > 0.6 && (
                    <div className="mt-1.5 pt-1.5 border-t border-border">
                        <div className="flex items-center justify-between text-[9px]">
                            <span className="text-muted-foreground">Impact</span>
                            <span className="font-mono font-bold">
                                {Math.round(importance * 100)}%
                            </span>
                        </div>
                        <div className="mt-0.5 h-1 bg-secondary rounded-full overflow-hidden">
                            <div
                                className="h-full transition-all duration-300"
                                style={{
                                    width: `${importance * 100}%`,
                                    backgroundColor: data.color,
                                }}
                            />
                        </div>
                    </div>
                )}

                {/* Selection indicator */}
                {isSelected && (
                    <div className="absolute -top-2 -right-2 w-5 h-5 bg-accent-pink border-2 border-border rounded-full flex items-center justify-center text-[10px] font-bold shadow-md">
                        ✓
                    </div>
                )}
            </div>

            {/* Output Handle */}
            <Handle
                type="source"
                position={Position.Bottom}
                style={{
                    width: 8,
                    height: 8,
                    background: data.color,
                    border: '2px solid #000',
                }}
            />
        </>
    );
};

export default memo(CustomNode);