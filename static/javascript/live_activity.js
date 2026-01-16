/**
 * Live Activity Widget
 * Connects to Supabase Realtime to show live user activity.
 */

document.addEventListener('DOMContentLoaded', async function () {
    // Check if configuration exists
    if (!window.FLASHCARDS_CONFIG || !window.FLASHCARDS_CONFIG.supabase_url) {
        console.error('Supabase configuration missing');
        return;
    }

    const { supabase_url, supabase_anon_key } = window.FLASHCARDS_CONFIG;

    // Initialize Supabase client
    const supabase = window.supabase.createClient(supabase_url, supabase_anon_key);

    const widgetContainer = document.getElementById('live-activity-widget');
    const listContainer = document.getElementById('live-activity-list');
    const toggleBtn = document.getElementById('live-activity-toggle-btn');
    const closeBtn = document.getElementById('live-activity-close-btn');
    const headerTitle = document.getElementById('live-activity-header'); // Clicking header also toggles

    // Max items to show
    const MAX_ITEMS = 3;

    // --- Persistence & State Logic ---

    // Check if user has closed the widget for this session
    if (sessionStorage.getItem('live_activity_hidden') === 'true') {
        widgetContainer.remove(); // Remove entirely
        return;
    }

    // Check if user has minimized the widget
    const isMinimized = localStorage.getItem('live_activity_minimized') === 'true';
    if (isMinimized) {
        widgetContainer.classList.add('minimized');
    }

    // --- Event Handlers ---

    // Toggle minimize/expand
    function toggleWidget() {
        widgetContainer.classList.toggle('minimized');
        const minimized = widgetContainer.classList.contains('minimized');
        localStorage.setItem('live_activity_minimized', minimized);
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent header click handling
            toggleWidget();
        });
    }

    // Allow clicking the header wrapper to toggle (except buttons)
    if (headerTitle) {
        headerTitle.addEventListener('click', (e) => {
            if (e.target !== closeBtn && e.target !== toggleBtn) {
                toggleWidget();
            }
        });
    }

    // Close widget for session
    if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            // No confirmation, just hide for session
            widgetContainer.style.opacity = '0';
            setTimeout(() => {
                widgetContainer.remove();
                sessionStorage.setItem('live_activity_hidden', 'true');
            }, 300);
        });
    }

    // --- Realtime Subscription ---

    const channel = supabase
        .channel('public:live_activity_logs')
        .on(
            'postgres_changes',
            {
                event: '*',
                schema: 'public',
                table: 'live_activity_logs'
            },
            (payload) => {
                // Handle both INSERT and UPDATE (and even DELETE if we wanted)
                // Both insert and update payloads have the 'new' record
                if (payload.new) {
                    handleNewActivity(payload.new);
                }
            }
        )
        .subscribe((status) => {
            console.log('Live Activity Status:', status);
        });

    // Fetch initial state (last 3 items)
    fetchInitialState();

    async function fetchInitialState() {
        // Only fetch if not hidden
        if (sessionStorage.getItem('live_activity_hidden') === 'true') return;

        const { data, error } = await supabase
            .from('live_activity_logs')
            .select('*')
            .order('answered_at', { ascending: false })
            .limit(MAX_ITEMS);

        if (error) {
            console.error('Error fetching live activity:', error);
            return;
        }

        if (data && data.length > 0) {
            // Reverse so we prepend strictly in order (oldest first, so newest ends up on top)
            // Actually handleNewActivity prepends, so if we iterate 0..N (newest..oldest), 
            // the newest (0) gets prepended first (bottom), then (1) above it... wait.
            // listContainer.prepend puts the element at the TOP.
            // If data is [Newest, Mid, Oldest]
            // We want the final list to be [Newest, Mid, Oldest]
            // 1. Process Oldest -> Prepend -> List: [Oldest]
            // 2. Process Mid -> Prepend -> List: [Mid, Oldest]
            // 3. Process Newest -> Prepend -> List: [Newest, Mid, Oldest]
            // So we need to process in reverse order: Oldest to Newest.

            const reversedData = [...data].reverse();
            reversedData.forEach(activity => {
                handleNewActivity(activity, false); // false = no animation for initial load?
            });
        }
    }

    /**
     * Handle a new activity event
     * @param {Object} activity - The activity log record
     * @param {Boolean} animate - Whether to animate the entry (default true)
     */
    function handleNewActivity(activity, animate = true) {
        // Show widget if it was concealed securely (hidden by default display:none in CSS/HTML)
        // Only show if not hidden for session
        if (sessionStorage.getItem('live_activity_hidden') !== 'true') {
            if (widgetContainer.style.display === 'none') {
                widgetContainer.style.display = 'block';
            }
        }

        const { user_id } = activity;

        // Deduplication: Remove existing item for this user
        const existingItem = listContainer.querySelector(`.live-activity-item[data-user-id="${user_id}"]`);
        if (existingItem) {
            existingItem.remove();
        }

        const itemElement = createActivityItem(activity);

        // Add to list (prepend to show latest at top)
        listContainer.prepend(itemElement);

        if (animate) {
            // Animate entrance
            // Force reflow
            void itemElement.offsetWidth;
            itemElement.classList.add('visible');
        } else {
            // Show immediately without animation class logic if wanted, 
            // OR just add visible immediately
            itemElement.classList.add('visible');
        }

        // Prune old items (keep max 3)
        const items = listContainer.children;
        if (items.length > MAX_ITEMS) {
            items[items.length - 1].remove();
        }

        // Ensure timer loop is running
        startTimerLoop();
    }

    /**
     * Create the DOM element for an activity item
     * @param {Object} activity 
     * @returns {HTMLElement}
     */
    function createActivityItem(activity) {
        const item = document.createElement('div');
        item.className = 'live-activity-item';
        // Add user ID for deduplication lookup
        item.setAttribute('data-user-id', activity.user_id);
        // Store timestamp for timer calculations
        item.setAttribute('data-timestamp', activity.answered_at || new Date().toISOString());

        // Extract data
        const { username, module_name, streak } = activity;

        const safeUsername = escapeHtml(username || 'Anonymous');
        const safeModule = escapeHtml(module_name || 'Generic Module');
        const safeStreak = parseInt(streak) || 1;

        // Determine fire intensity
        let fireIcon = '🔥';
        if (safeStreak > 5) fireIcon = '🔥🔥';
        if (safeStreak > 10) fireIcon = '🔥🔥🔥';

        const userLink = `/user_stats/${activity.user_id}`;

        item.innerHTML = `
            <div class="activity-avatar">
                ${safeUsername.charAt(0).toUpperCase()}
            </div>
            <div class="activity-content">
                <div class="activity-text">
                    <a href="${userLink}" class="activity-user-link">${safeUsername}</a> 
                    answered in 
                    <span class="activity-module">${safeModule}</span>
                </div>
                <div class="activity-meta">
                    <span class="activity-streak">${fireIcon} Streak: ${safeStreak}</span>
                    <span class="activity-time">Just now</span>
                </div>
            </div>
        `;

        return item;
    }

    // Helper to escape HTML characters
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // --- Timer Logic ---
    let timerInterval = null;

    function formatTimeAgo(date) {
        const now = new Date();
        const diffSeconds = Math.floor((now - date) / 1000);

        if (diffSeconds < 60) {
            return diffSeconds <= 0 ? 'Just now' : `${diffSeconds}s ago`;
        }

        const diffMinutes = Math.floor(diffSeconds / 60);
        if (diffMinutes < 60) {
            return `${diffMinutes}m ago`;
        }

        const diffHours = Math.floor(diffMinutes / 60);
        if (diffHours < 24) {
            return `${diffHours}h ago`;
        }

        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 30) {
            return `${diffDays}d ago`;
        }

        const diffMonths = Math.floor(diffDays / 30);
        return `${diffMonths}mo ago`;
    }

    function startTimerLoop() {
        if (timerInterval) return; // Already running

        timerInterval = setInterval(() => {
            const items = listContainer.querySelectorAll('.live-activity-item');

            if (items.length === 0) {
                // If empty, hide widget and stop timer
                widgetContainer.style.display = 'none';
                clearInterval(timerInterval);
                timerInterval = null;
                return;
            }

            // Expiry logic REMOVED. Items stay until pushed out by new ones.

            items.forEach(item => {
                const timestampStr = item.getAttribute('data-timestamp');
                if (!timestampStr) return;

                const time = new Date(timestampStr);

                // Update text
                const timeSpan = item.querySelector('.activity-time');
                if (timeSpan) {
                    timeSpan.textContent = formatTimeAgo(time);
                }
            });

        }, 1000);
    }
});
