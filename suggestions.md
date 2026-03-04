middle section for analytics
- total nodes
- total connections

pre-made filters
- by team
- by step type
- by TTP

configurable filters
- communication dotted lines
- direct connection lines
- filter certain types of artifacts
- filter out certain types of edges



                        {/* Mode Toggle */}
                        <div className="neo-card p-1 flex gap-1 bg-card">
                            <button
                                onClick={() => onModeChange('mining')}
                                className={`px-4 py-2 rounded-lg font-semibold transition-all flex items-center gap-2 ${mode === 'mining'
                                    ? 'bg-primary text-primary-foreground shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
                                    : 'bg-transparent hover:bg-muted text-foreground'
                                    }`}
                            >
                                <Pickaxe className="w-4 h-4" />

                            </button>
                            <button
                                onClick={() => onModeChange('discovery')}
                                className={`px-4 py-2 rounded-lg font-semibold transition-all flex items-center gap-2 ${mode === 'discovery'
                                    ? 'bg-accent-pink text-foreground shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
                                    : 'bg-transparent hover:bg-muted text-foreground'
                                    }`}
                            >
                                <Gem className="w-4 h-5" />

                            </button>
                        </div>