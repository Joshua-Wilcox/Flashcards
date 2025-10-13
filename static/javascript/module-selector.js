/**
 * Module Selector Component
 * Supports grouping modules by academic year with a two-step selection UI.
 */

class ModuleSelector {
    constructor(options = {}) {
        this.containerId = options.containerId || 'module-selector';
        this.onModuleChange = options.onModuleChange || (() => {});
        this.allowDeselect = options.allowDeselect !== false; // Default true

        this.$container = $(`#${this.containerId}-container`);
        this.$dropdownRoot = this.$container.find('.module-selector-root');
        this.$button = $(`#${this.containerId}-dropdown`);
        this.$menu = $(`#${this.containerId}-dropdown-menu`);

        this.selectedModule = options.selectedModule || this._getDatasetValue('selected-module', '');
        this.modules = options.modules || this._getDatasetValue('modules', []);
        this.moduleGroups = options.moduleGroups || this._getDatasetValue('module-groups', []);

        this.normalizedGroups = this._normalizeGroups(this.moduleGroups, this.modules);
        this.moduleLookup = this._buildModuleLookup(this.normalizedGroups);

        // Drop selection if module no longer exists
        if (this.selectedModule && !this.moduleLookup[this.selectedModule]) {
            this.selectedModule = '';
        }

        this.activeGroupKey = this.selectedModule ? this.moduleLookup[this.selectedModule]?.groupKey || null : null;

        this._bindEvents();
        this.renderMenu();
        this.updateLabel();
        this.updateSelection();
    }

    /**
     * Retrieve data attribute value from the dropdown root
     * @private
     */
    _getDatasetValue(attr, defaultValue) {
        if (!this.$dropdownRoot.length) {
            return defaultValue;
        }

        const value = this.$dropdownRoot.data(attr);
        if (value === undefined) {
            return defaultValue;
        }

        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (!trimmed) {
                return defaultValue;
            }
            try {
                // Attempt JSON parsing (covers arrays/objects)
                return JSON.parse(trimmed);
            } catch (err) {
                // Fall back to raw string for simple values
                return trimmed;
            }
        }

        return value;
    }

    /**
     * Normalise groups/mods from backend or fallback to building groups locally
     * @private
     */
    _normalizeGroups(groups, modules) {
        const hasGroups = Array.isArray(groups) && groups.length > 0;
        const normalizedModules = this._normalizeModules(
            hasGroups ? groups.flatMap(group => group.modules || []) : modules
        );

        if (hasGroups) {
            // Rebuild groups to ensure consistent structure/order
            return this._buildGroupsFromModules(normalizedModules, groups);
        }

        return this._buildGroupsFromModules(normalizedModules);
    }

    /**
     * Ensure modules share a consistent structure
     * @private
     */
    _normalizeModules(modules) {
        if (!Array.isArray(modules)) {
            return [];
        }

        const deduped = new Map();

        modules.filter(Boolean).forEach((item) => {
            let name;
            let rawYear = null;
            let id = null;

            if (typeof item === 'string') {
                name = item;
            } else {
                name = item.name || item.module || '';
                rawYear = item.year !== undefined ? item.year : null;
                id = item.id ?? null;
            }

            if (!name) {
                return;
            }

            const year = Number.isInteger(rawYear)
                ? rawYear
                : Number.isFinite(parseInt(rawYear, 10))
                    ? parseInt(rawYear, 10)
                    : null;

            if (!deduped.has(name)) {
                deduped.set(name, { id, name, year });
            } else {
                const existing = deduped.get(name);
                // Prefer non-null IDs and years
                if (existing.id === null && id !== null) {
                    existing.id = id;
                }
                if (existing.year === null && year !== null) {
                    existing.year = year;
                }
            }
        });

        return Array.from(deduped.values());
    }

    /**
     * Build grouped structure from modules, optionally guided by backend groups
     * @private
     */
    _buildGroupsFromModules(modules, existingGroups = null) {
        const map = new Map();

        const ensureGroup = (key, label, year) => {
            if (!map.has(key)) {
                map.set(key, {
                    key,
                    label,
                    year,
                    modules: []
                });
            }
            return map.get(key);
        };

        if (Array.isArray(existingGroups) && existingGroups.length) {
            existingGroups.forEach((group) => {
                const rawYear = group.year !== undefined ? group.year : null;
                const year = Number.isInteger(rawYear)
                    ? rawYear
                    : Number.isFinite(parseInt(rawYear, 10))
                        ? parseInt(rawYear, 10)
                        : null;
                const key = group.key || (year !== null ? `year-${year}` : 'other');
                const label = group.label || (year !== null ? `Year ${year}` : 'Other Modules');
                ensureGroup(key, label, year);
            });
        }

        modules.forEach((module) => {
            const year = module.year;
            const key = year !== null ? `year-${year}` : 'other';
            const label = year !== null ? `Year ${year}` : 'Other Modules';
            ensureGroup(key, label, year).modules.push(module);
        });

        const groups = Array.from(map.values());
        groups.forEach((group) => {
            group.modules.sort((a, b) => a.name.localeCompare(b.name));
        });

        groups.sort((a, b) => {
            const aOther = a.year === null;
            const bOther = b.year === null;
            if (aOther !== bOther) {
                return aOther ? 1 : -1;
            }
            if (a.year === null && b.year === null) {
                return 0;
            }
            return a.year - b.year;
        });

        return groups;
    }

    /**
     * Build lookup map for module -> group metadata
     * @private
     */
    _buildModuleLookup(groups) {
        const lookup = {};
        groups.forEach((group) => {
            const yearLabel = group.year !== null ? group.label : null;
            group.modules.forEach((module) => {
                lookup[module.name] = {
                    groupKey: group.key,
                    year: group.year,
                    yearLabel
                };
            });
        });
        return lookup;
    }

    /**
     * Attach DOM event handlers (scoped per instance)
     * @private
     */
    _bindEvents() {
        const menuSelector = `#${this.containerId}-dropdown-menu`;

        $(document)
            .off('click', `${menuSelector} .dropdown-item-module`)
            .on('click', `${menuSelector} .dropdown-item-module`, (event) => {
                this._handleModuleClick(event);
            });

        $(document)
            .off('click', `${menuSelector} .module-year-item`)
            .on('click', `${menuSelector} .module-year-item`, (event) => {
                event.preventDefault();
                event.stopPropagation();
                const groupKey = $(event.currentTarget).data('group-key');
                console.log('Year item clicked:', groupKey); // Debug log
                this.activeGroupKey = groupKey || null;
                this.renderMenu();
                this.updateSelection();
                // Keep dropdown open
                return false;
            });

        $(document)
            .off('click', `${menuSelector} .module-year-back`)
            .on('click', `${menuSelector} .module-year-back`, (event) => {
                event.preventDefault();
                event.stopPropagation();
                console.log('Back button clicked'); // Debug log
                this.activeGroupKey = null;
                this.renderMenu();
                this.updateSelection();
                // Keep dropdown open
                return false;
            });

        $(document)
            .off('click', `${menuSelector} .module-selector-clear`)
            .on('click', `${menuSelector} .module-selector-clear`, (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.selectedModule = '';
                this.activeGroupKey = null;
                this.updateLabel();
                this.renderMenu();
                this.updateSelection();
                this.onModuleChange(this.selectedModule);
                if (typeof bootstrap !== 'undefined' && this.$button.length) {
                    const dropdown = bootstrap.Dropdown.getOrCreateInstance(this.$button[0]);
                    dropdown.hide();
                } else if (this.$button.length && typeof this.$button.dropdown === 'function') {
                    this.$button.dropdown('hide');
                }
            });

        this.$button.off('show.bs.dropdown').on('show.bs.dropdown', () => {
            this.activeGroupKey = this.selectedModule
                ? this.moduleLookup[this.selectedModule]?.groupKey || null
                : null;
            this.renderMenu();
            this.updateSelection();
        });
    }

    /**
     * Handle module selection clicks
     * @private
     */
    _handleModuleClick(event) {
        const value = $(event.currentTarget).data('value');
        if (!value) {
            return;
        }

        if (this.allowDeselect && this.selectedModule === value) {
            this.selectedModule = '';
            this.activeGroupKey = null;
        } else {
            this.selectedModule = value;
            this.activeGroupKey = this.moduleLookup[value]?.groupKey || null;
        }

        this.updateLabel();
        this.updateSelection();
        this.onModuleChange(this.selectedModule);
        
        // Close dropdown after module selection
        if (typeof bootstrap !== 'undefined' && this.$button.length) {
            const dropdown = bootstrap.Dropdown.getOrCreateInstance(this.$button[0]);
            dropdown.hide();
        } else if (this.$button.length && typeof this.$button.dropdown === 'function') {
            this.$button.dropdown('hide');
        }
    }

    /**
     * Render dropdown menu based on current view (year list or modules)
     */
    renderMenu() {
        if (!this.$menu.length) {
            return;
        }

        this.$menu.empty();
        this.$menu.removeClass('module-selector-years-view module-selector-modules-view');

        if (!this.normalizedGroups.length) {
            this.$menu.append('<li class="px-3 py-2 text-muted">No modules available</li>');
            return;
        }

        if (!this.activeGroupKey) {
            this.$menu.addClass('module-selector-years-view');

            if (this.allowDeselect && this.selectedModule) {
                this.$menu.append(`
                    <li>
                        <div class="dropdown-item module-selector-clear" role="button">
                            Clear module selection
                        </div>
                    </li>
                    <li><hr class="dropdown-divider"></li>
                `);
            }

            this.normalizedGroups.forEach((group) => {
                const moduleCount = group.modules.length;
                this.$menu.append(`
                    <li>
                        <div class="dropdown-item module-year-item" role="button" data-group-key="${group.key}">
                            <span class="module-year-label">${group.label}</span>
                            <span class="module-year-meta">${moduleCount} module${moduleCount === 1 ? '' : 's'}</span>
                            <span class="module-year-chevron" aria-hidden="true">›</span>
                        </div>
                    </li>
                `);
            });
        } else {
            this.$menu.addClass('module-selector-modules-view');
            const group = this.normalizedGroups.find((g) => g.key === this.activeGroupKey);
            if (!group) {
                this.activeGroupKey = null;
                this.renderMenu();
                return;
            }

            this.$menu.append(`
                <li>
                    <div class="dropdown-item module-year-back" role="button">← All years</div>
                </li>
                <li><hr class="dropdown-divider"></li>
            `);

            if (!group.modules.length) {
                this.$menu.append(`
                    <li class="px-3 py-2 text-muted">No modules in ${group.label}</li>
                `);
                return;
            }

            group.modules.forEach((module) => {
                this.$menu.append(`
                    <li>
                        <div class="dropdown-item-module" data-value="${module.name}" data-group-key="${group.key}">
                            ${module.name}
                        </div>
                    </li>
                `);
            });
        }
    }

    /** Update button label to reflect selection */
    updateLabel() {
        if (!this.$button.length) {
            return;
        }

        if (!this.selectedModule) {
            this.$button.text('Select Module');
            return;
        }

        const meta = this.moduleLookup[this.selectedModule];
        if (meta && meta.yearLabel) {
            this.$button.text(`${this.selectedModule} (${meta.yearLabel})`);
        } else {
            this.$button.text(this.selectedModule);
        }
    }

    /** Highlight currently selected module in the menu */
    updateSelection() {
        const menuSelector = `#${this.containerId}-dropdown-menu .dropdown-item-module`;
        $(menuSelector).each((_, element) => {
            const $el = $(element);
            const value = $el.data('value');
            if (value === this.selectedModule) {
                $el.addClass('selected').attr('aria-selected', 'true');
            } else {
                $el.removeClass('selected').attr('aria-selected', 'false');
            }
        });
    }

    /** Programmatically set module selection */
    setModule(module) {
        this.selectedModule = module || '';
        this.activeGroupKey = this.selectedModule
            ? this.moduleLookup[this.selectedModule]?.groupKey || null
            : null;
        this.updateLabel();
        this.renderMenu();
        this.updateSelection();
    }

    /** Retrieve current module */
    getModule() {
        return this.selectedModule;
    }

    /** Enable/disable selector */
    setDisabled(disabled) {
        this.$button.prop('disabled', disabled);
    }
}

// expose globally
window.ModuleSelector = ModuleSelector;
