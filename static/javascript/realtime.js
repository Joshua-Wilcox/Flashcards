// Initialize Supabase client
const supabaseUrl = window.SUPABASE_URL || 'http://localhost:54321';
const supabaseKey = window.SUPABASE_ANON_KEY;
const supabase = window.supabase.createClient(supabaseUrl, supabaseKey);

class RealtimeManager {
    constructor() {
        this.channels = new Map();
        this.isConnected = false;
    }

    // Subscribe to leaderboard updates
    subscribeToLeaderboard(callback) {
        const channel = supabase.channel('leaderboard-updates')
            .on('postgres_changes', 
                { event: '*', schema: 'public', table: 'user_stats' },
                callback
            )
            .on('postgres_changes', 
                { event: '*', schema: 'public', table: 'module_stats' },
                callback
            )
            .subscribe();
        
        this.channels.set('leaderboard', channel);
        return channel;
    }

    // Subscribe to user-specific updates
    subscribeToUserUpdates(userId, callback) {
        const channel = supabase.channel(`user-${userId}-updates`)
            .on('postgres_changes',
                { 
                    event: '*', 
                    schema: 'public', 
                    table: 'user_stats',
                    filter: `user_id=eq.${userId}`
                },
                callback
            )
            .subscribe();
        
        this.channels.set(`user-${userId}`, channel);
        return channel;
    }

    // Subscribe to live activity feed
    subscribeToActivity(callback) {
        const channel = supabase.channel('activity-feed')
            .on('postgres_changes',
                { event: 'UPDATE', schema: 'public', table: 'user_stats' },
                (payload) => {
                    // Only show if total_answers increased (new answer submitted)
                    if (payload.new.total_answers > payload.old.total_answers) {
                        callback({
                            type: 'answer_submitted',
                            user: payload.new.username,
                            correct: payload.new.correct_answers > payload.old.correct_answers,
                            timestamp: new Date()
                        });
                    }
                }
            )
            .subscribe();
        
        this.channels.set('activity', channel);
        return channel;
    }

    unsubscribe(channelName) {
        const channel = this.channels.get(channelName);
        if (channel) {
            supabase.removeChannel(channel);
            this.channels.delete(channelName);
        }
    }

    unsubscribeAll() {
        this.channels.forEach((channel, name) => {
            supabase.removeChannel(channel);
        });
        this.channels.clear();
    }
}

// Global realtime manager
window.realtimeManager = new RealtimeManager();
