   // Image upload preview functionality with drag and drop
class ImageUploader {
    constructor(config) {
        this.dropZone = document.getElementById(config.dropZoneId);
        this.fileInput = document.getElementById(config.fileInputId);
        this.previewContainer = document.getElementById(config.previewContainerId);
        this.maxFiles = config.maxFiles || 12;
        this.allFiles = [];

        this.init();
    }

    init() {
        this.preventDefaults();
        this.setupDropEvents();
        this.fileInput.addEventListener('change', () => this.handleFiles(this.fileInput.files));
    }

    preventDefaults() {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, e => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });
    }

    setupDropEvents() {
        ['dragenter', 'dragover'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, () => this.highlight(), false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, () => this.unhighlight(), false);
        });

        this.dropZone.addEventListener('drop', (e) => this.handleDrop(e), false);
    }

    highlight() {
        this.dropZone.classList.add('drop-zone-highlight');
    }

    unhighlight() {
        this.dropZone.classList.remove('drop-zone-highlight');
    }

    handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        this.handleFiles(files);
    }

    handleFiles(newFiles) {
        const incoming = Array.from(newFiles);

        for (let file of incoming) {
            if (this.allFiles.length >= this.maxFiles) break;
            if (file.type.match('image.*')) {
                this.allFiles.push(file);
            }
        }

        this.syncFileInput();
        this.renderPreviews();
    }

    syncFileInput() {
        const dataTransfer = new DataTransfer();
        this.allFiles.forEach(file => dataTransfer.items.add(file));
        this.fileInput.files = dataTransfer.files;
    }

    renderPreviews() {
        this.previewContainer.innerHTML = '';

        if (this.allFiles.length === 0) {
            this.previewContainer.innerHTML = `
                <p class="text-sm text-gray-500 col-span-2 sm:col-span-3 text-center py-4">
                    No images selected
                </p>
            `;
            return;
        }

        this.allFiles.forEach((file, index) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const div = document.createElement('div');
                div.className = 'relative group';
                div.innerHTML = `
                    <img src="${e.target.result}" alt="Preview" class="w-full h-32 object-cover rounded-lg">
                    <button type="button" class="absolute top-1 right-1 bg-white/80 text-red-500 p-0.5 rounded-full hover:bg-white transition" data-index="${index}">
                        <i class="fas fa-times text-2xs"></i>
                    </button>
                    <div class="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-2xs p-0.5 truncate">${file.name}</div>
                `;
                this.previewContainer.appendChild(div);

                div.querySelector('button').addEventListener('click', (btnEvent) => {
                    const removeIndex = parseInt(btnEvent.currentTarget.getAttribute('data-index'));
                    this.allFiles.splice(removeIndex, 1);
                    this.syncFileInput();
                    this.renderPreviews(); // Re-render previews
                });
            };
            reader.readAsDataURL(file);
        });
    }
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    new ImageUploader({
        dropZoneId: 'drop-zone',
        fileInputId: 'property_images',
        previewContainerId: 'image-preview-container',
        maxFiles: 12
    });
});



class AmenitySelector {
    constructor(config) {
        this.max = config.max || 10;

        // Elements
        this.searchInput = document.getElementById(config.searchId);
        this.dropdown = document.getElementById(config.dropdownId);
        this.options = Array.from(document.querySelectorAll(config.optionSelector));
        this.selectedContainer = document.getElementById(config.selectedContainerId);
        this.hiddenInput = document.getElementById(config.hiddenInputId);
        this.limitMessage = document.getElementById(config.limitMessageId);
        this.quickBtns = document.querySelectorAll(config.quickBtnSelector);

        // Internal state
        this.selectedIds = new Set();

        this.init();
    }

    init() {
        this.loadInitialSelections();
        this.setupEventListeners();
    }

    loadInitialSelections() {
        const selectedOptions = this.hiddenInput.querySelectorAll('option[selected]');
        selectedOptions.forEach(option => {
            const id = option.value;
            const amenity = this.options.find(opt => opt.dataset.id === id);
            if (amenity) {
                this.addAmenity(amenity.dataset.id, amenity.dataset.name, amenity.dataset.icon);
            }
        });

        if (this.selectedIds.size === 0) {
            this.showPlaceholder();
        }
    }

    setupEventListeners() {
        // Dropdown toggle and search
        this.searchInput.addEventListener('focus', () => {
            this.dropdown.classList.remove('hidden');
            this.filterOptions();
        });

        this.searchInput.addEventListener('input', () => this.filterOptions());

        document.addEventListener('click', (e) => {
            if (!e.target.closest(`#${this.searchInput.id}`) && !e.target.closest(`#${this.dropdown.id}`)) {
                this.dropdown.classList.add('hidden');
            }
        });

        // Option click
        this.options.forEach(option => {
            option.addEventListener('click', () => {
                this.addAmenity(option.dataset.id, option.dataset.name, option.dataset.icon);
                this.searchInput.value = '';
                this.filterOptions();
                this.dropdown.classList.add('hidden');
            });
        });

        // Quick buttons
        this.quickBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                this.addAmenity(btn.dataset.id, btn.dataset.name, btn.dataset.icon);
            });
        });
    }

    addAmenity(id, name, icon) {
        if (this.selectedIds.has(id)) return;

        if (this.selectedIds.size >= this.max) {
            this.limitMessage.classList.remove('hidden');
            return;
        }

        this.limitMessage.classList.add('hidden');
        this.selectedIds.add(id);
        this.removePlaceholder();

        // Create chip
        const chip = document.createElement('span');
        chip.className = 'inline-flex items-center px-2 sm:px-3 py-0.5 sm:py-1 bg-primary-600 text-white rounded-full text-xs sm:text-sm';
        chip.innerHTML = `
            <i class="${icon} mr-1 text-xs sm:text-sm"></i>${name}
            <button type="button" class="ml-1 sm:ml-2 text-white hover:text-primary-200 remove-amenity">
                <i class="fas fa-times text-2xs sm:text-xs"></i>
            </button>
        `;

        this.selectedContainer.appendChild(chip);

        // Add to hidden select
        const option = document.createElement('option');
        option.value = id;
        option.selected = true;
        this.hiddenInput.appendChild(option);

        // Remove functionality
        chip.querySelector('.remove-amenity').addEventListener('click', () => {
            this.removeAmenity(id, chip, option);
        });
    }

    removeAmenity(id, chip, option) {
        chip.remove();
        option.remove();
        this.selectedIds.delete(id);
        this.limitMessage.classList.add('hidden');

        if (this.selectedIds.size === 0) {
            this.showPlaceholder();
        }
    }

    filterOptions() {
        const term = this.searchInput.value.toLowerCase();
        this.options.forEach(option => {
            const name = option.dataset.name.toLowerCase();
            option.style.display = name.includes(term) ? 'flex' : 'none';
        });
    }

    showPlaceholder() {
        this.selectedContainer.innerHTML = '<p class="text-xs sm:text-sm text-gray-500 self-center">No amenities selected yet</p>';
    }

    removePlaceholder() {
        const placeholder = this.selectedContainer.querySelector('p.text-gray-500');
        if (placeholder) this.selectedContainer.innerHTML = '';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new AmenitySelector({
        searchId: 'amenity-search',
        dropdownId: 'amenity-dropdown',
        optionSelector: '.amenity-option',
        selectedContainerId: 'selected-amenities',
        hiddenInputId: 'amenities-input',
        limitMessageId: 'amenity-limit-message',
        quickBtnSelector: '.quick-amenity-btn',
        max: 10
    });
});
