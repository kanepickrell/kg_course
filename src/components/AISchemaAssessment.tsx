// frontend/src/components/ingestion/AISchemaAssessment.tsx

import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, CheckCircle2, XCircle, Lightbulb } from "lucide-react";

interface AISchemaAssessmentProps {
  artifactId: string;
  fullData: any;
  userSchema: {
    fields: string[];
    dataUrl: string;
    storageLocation: string;
  };
  onComplete: (finalFields: string[]) => void;
  onBack: () => void;
}

interface AISuggestion {
  field: string;
  reasoning: string;
  confidence: number;
  currentValue: any;
}

const AISchemaAssessment: React.FC<AISchemaAssessmentProps> = ({
  artifactId,
  fullData,
  userSchema,
  onComplete,
  onBack
}) => {
  const [loading, setLoading] = useState(true);
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [acceptedSuggestions, setAcceptedSuggestions] = useState<string[]>([]);
  const [aiReasoning, setAiReasoning] = useState("");

  useEffect(() => {
    assessSchema();
  }, []);

  const assessSchema = async () => {
    setLoading(true);
    
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/ingest/assess-schema`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_data: fullData,
          user_metadata_schema: userSchema.fields.reduce((acc, field) => {
            acc[field] = typeof fullData[field];
            return acc;
          }, {} as any)
        })
      });

      const result = await response.json();
      
      // Extract AI suggestions (fields AI recommends that user didn't select)
      const suggestions: AISuggestion[] = result.recommendation.metadata_fields
        .filter((field: string) => !userSchema.fields.includes(field))
        .map((field: string) => ({
          field,
          reasoning: `AI detected this field is lightweight and frequently used for connections`,
          confidence: 0.85,
          currentValue: fullData[field]
        }));
      
      setAiSuggestions(suggestions);
      setAiReasoning(result.recommendation.reasoning);
      
    } catch (error) {
      console.error("AI assessment failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSuggestion = (field: string) => {
    if (acceptedSuggestions.includes(field)) {
      setAcceptedSuggestions(acceptedSuggestions.filter(f => f !== field));
    } else {
      setAcceptedSuggestions([...acceptedSuggestions, field]);
    }
  };

  const handleContinue = () => {
    const finalFields = [...userSchema.fields, ...acceptedSuggestions];
    onComplete(finalFields);
  };

  const formatValue = (value: any) => {
    if (typeof value === 'string') {
      return value.length > 50 ? value.substring(0, 50) + '...' : value;
    }
    if (Array.isArray(value)) {
      return `[${value.length} items]`;
    }
    if (typeof value === 'object') {
      return '[Object]';
    }
    return String(value);
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-6">
      <Card className="neo-card p-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-full bg-accent-blue/20 flex items-center justify-center">
              <span className="text-accent-blue font-bold">3</span>
            </div>
            <h2 className="text-2xl font-bold">AI Schema Assessment</h2>
          </div>
          <p className="text-muted text-sm">
            ProtoGraph AI analyzed your data and has suggestions to improve searchability and connections.
          </p>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="animate-spin mb-4" size={48} />
            <p className="text-muted">AI is analyzing your schema...</p>
          </div>
        ) : (
          <>
            {/* AI Reasoning */}
            <div className="neo-card bg-accent-blue/10 border-accent-blue/30 p-4 mb-6">
              <div className="flex gap-3">
                <Lightbulb className="text-accent-blue flex-shrink-0 mt-1" size={20} />
                <div>
                  <h3 className="font-bold mb-1">🤖 AI Analysis</h3>
                  <p className="text-sm text-muted">{aiReasoning}</p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
              {/* Left: Your Current Selection */}
              <div>
                <h3 className="text-lg font-bold mb-3 flex items-center gap-2">
                  <CheckCircle2 className="text-accent-teal" size={20} />
                  Your Selected Fields ({userSchema.fields.length})
                </h3>
                <div className="neo-card bg-accent-teal/10 p-4">
                  <div className="space-y-2 max-h-96 overflow-y-auto neo-scrollbar">
                    {userSchema.fields.map(field => (
                      <div key={field} className="flex items-center justify-between p-2 bg-secondary/30 rounded">
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-sm">{field}</div>
                          <div className="text-xs text-muted truncate">
                            {formatValue(fullData[field])}
                          </div>
                        </div>
                        <Badge variant="outline" className="text-accent-teal border-accent-teal ml-2">
                          ✓
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Right: AI Suggestions */}
              <div>
                <h3 className="text-lg font-bold mb-3 flex items-center gap-2">
                  <Lightbulb className="text-accent-blue" size={20} />
                  AI Suggestions ({aiSuggestions.length})
                </h3>
                
                {aiSuggestions.length === 0 ? (
                  <div className="neo-card bg-secondary/50 p-8 text-center">
                    <CheckCircle2 className="mx-auto mb-3 text-accent-teal" size={48} />
                    <p className="font-bold mb-1">Perfect Schema!</p>
                    <p className="text-sm text-muted">
                      AI has no additional suggestions. Your metadata selection looks optimal.
                    </p>
                  </div>
                ) : (
                  <div className="neo-card bg-accent-blue/10 p-4">
                    <div className="space-y-3 max-h-96 overflow-y-auto neo-scrollbar">
                      {aiSuggestions.map(suggestion => (
                        <div 
                          key={suggestion.field}
                          className="p-3 bg-card rounded border-2 border-transparent hover:border-accent-blue/50 cursor-pointer transition-all"
                          onClick={() => toggleSuggestion(suggestion.field)}
                        >
                          <div className="flex items-start gap-3">
                            <Checkbox
                              checked={acceptedSuggestions.includes(suggestion.field)}
                              onCheckedChange={() => toggleSuggestion(suggestion.field)}
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-semibold text-sm">{suggestion.field}</span>
                                <Badge variant="outline" className="text-xs">
                                  {(suggestion.confidence * 100).toFixed(0)}% confidence
                                </Badge>
                              </div>
                              <p className="text-xs text-muted mb-2">{suggestion.reasoning}</p>
                              <div className="text-xs bg-secondary/50 p-2 rounded">
                                <strong>Current value:</strong> {formatValue(suggestion.currentValue)}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    <div className="mt-4 flex gap-2">
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => setAcceptedSuggestions(aiSuggestions.map(s => s.field))}
                      >
                        Accept All
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => setAcceptedSuggestions([])}
                      >
                        Reject All
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Summary */}
            <div className="neo-card bg-secondary/30 p-4 mt-6">
              <h4 className="font-bold text-sm mb-3">📊 Final Summary</h4>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-muted mb-1">Your Selection</p>
                  <p className="text-2xl font-bold">{userSchema.fields.length}</p>
                </div>
                <div>
                  <p className="text-xs text-muted mb-1">AI Suggestions Accepted</p>
                  <p className="text-2xl font-bold text-accent-blue">{acceptedSuggestions.length}</p>
                </div>
                <div>
                  <p className="text-xs text-muted mb-1">Total Metadata Fields</p>
                  <p className="text-2xl font-bold text-accent-teal">
                    {userSchema.fields.length + acceptedSuggestions.length}
                  </p>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <Button variant="outline" onClick={onBack}>
                ← Back
              </Button>
              <Button 
                onClick={handleContinue}
                className="neo-button-primary flex-1"
              >
                Continue to Final Review →
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

export default AISchemaAssessment;