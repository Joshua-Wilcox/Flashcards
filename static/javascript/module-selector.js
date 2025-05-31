/**
 * Module Selector Component
 * Reusable module selection logic that can be shared across pages
 */

class ModuleSelector {
    constructor(options = {}) {
        this.containerId = options.containerId || 'module-selector';
        this.selectedModule = options.selectedModule || '';
        this.onModuleChange = options.onModuleChange || (() => {});
        this.allowDeselect = options.allowDeselect !== false; // Default to true
        
        this.init();
    }
    
    init() {
        this.updateLabel();
        this.updateSelection();
        this.bindEvents();
    }
    
    bindEvents() {
        // Handle module selection
        $(document).on('click', `#${this.containerId}-dropdown-menu .dropdown-item-module`, (e) => {
            const value = $(e.target).data('value');
            
            if (this.allowDeselect && this.selectedModule === value) {
                this.selectedModule = '';
            } else {
                this.selectedModule = value;
            }
            
            this.updateLabel();
            this.updateSelection();
            
            // Call the callback with the new selection
            this.onModuleChange(this.selectedModule);
        });
        
        // Prevent dropdown from closing on selection
        $(document).on('mousedown', `#${this.containerId}-dropdown-menu .dropdown-item-module`, (e) => {
            e.preventDefault();
        });
        
        // Update label and selection on dropdown show
        $(`#${this.containerId}-dropdown`).on('show.bs.dropdown', () => {
            this.updateLabel();
            this.updateSelection();
        });
    }
    
    updateLabel() {
        const $btn = $(`#${this.containerId}-dropdown`);
        if (!this.selectedModule) {
            $btn.text('Select Module');
        } else {
            $btn.text(this.selectedModule);
        }
    }
    
    updateSelection() {
        $(`#${this.containerId}-dropdown-menu .dropdown-item-module`).each((index, element) => {
            const val = $(element).data('value');
            if (val === this.selectedModule) {
                $(element).addClass('selected').attr('aria-selected', 'true');
            } else {
                $(element).removeClass('selected').attr('aria-selected', 'false');
            }
        });
    }
    
    setModule(module) {
        this.selectedModule = module;
        this.updateLabel();
        this.updateSelection();
    }
    
    getModule() {
        return this.selectedModule;
    }
    
    setDisabled(disabled) {
        $(`#${this.containerId}-dropdown`).prop('disabled', disabled);
    }
}

// Make it available globally
window.ModuleSelector = ModuleSelector;
