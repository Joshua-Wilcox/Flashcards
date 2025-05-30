// Apply hiding logic before any other code runs
(function () {
    if (localStorage.getItem('never-show-payment-widget') === 'true') {
        const widget = document.getElementById('stripe-widget');
        if (widget) widget.classList.add('preload-hidden');
    } else {
        // Only remove preload-hidden if user hasn't opted out
        const widget = document.getElementById('stripe-widget');
        if (widget) widget.classList.remove('preload-hidden');
    }
})();

let currentSelections = {
    module: '',
    topics: [],
    subtopics: [],
    tags: []
};
let currentQuestionToken = null; // Store the token for the current question
let isAdmin = false;
let currentQuestionId = null;
// --- Delay answers state ---
let delayAnswersSeconds = 0;
let delayInterval = null;
// Try to persist delay value in localStorage
if (localStorage.getItem('delayAnswersSeconds')) {
    delayAnswersSeconds = parseInt(localStorage.getItem('delayAnswersSeconds')) || 0;
}

// Set input value on load
$(document).ready(function () {
    $('#delay-answers-input').val(delayAnswersSeconds);
});

// Update delay value on change
$('#delay-answers-input').on('input', function () {
    let val = parseInt($(this).val()) || 0;
    if (val < 0) val = 0;
    if (val > 60) val = 60;
    delayAnswersSeconds = val;
    localStorage.setItem('delayAnswersSeconds', delayAnswersSeconds);
    $(this).val(delayAnswersSeconds);
});

// Helper: show/hide answer buttons with delay
function showAnswerButtonsWithDelay() {
    // Always clear any previous countdown before starting a new one
    if (delayInterval) {
        clearInterval(delayInterval);
        delayInterval = null;
    }
    $('#delay-countdown').remove();

    if (delayAnswersSeconds > 0) {
        $('.answer-btn').hide();
        let $container = $('#answers-container');
        let countdown = delayAnswersSeconds;
        let paused = false;
        let $countdownDiv = $('#delay-countdown');
        if ($countdownDiv.length === 0) {
            $countdownDiv = $('<div id="delay-countdown" class="text-center text-muted mb-2" style="font-size:1.1em;"></div>');
            $container.prepend($countdownDiv);
        }
        function renderCountdown() {
            if (paused) {
                $countdownDiv.html(
                    `<span><b>Paused</b></span>
                    <button id="skip-delay-btn" class="delay-action-btn ms-2">Show answers now</button>`
                );
            } else {
                $countdownDiv.html(
                    `<span>Showing answers in <b>${countdown}</b> second${countdown !== 1 ? 's' : ''}...</span>
                    <button id="pause-delay-btn" class="delay-action-btn pause ms-2">Pause</button>
                    <button id="skip-delay-btn" class="delay-action-btn ms-2">Show answers now</button>`
                );
            }
        }
        renderCountdown();
        delayInterval = setInterval(function () {
            if (!paused) {
                countdown--;
                if (countdown <= 0) {
                    clearInterval(delayInterval);
                    delayInterval = null;
                    $countdownDiv.remove();
                    $('.answer-btn').show();
                } else {
                    renderCountdown();
                }
            }
        }, 1000);
        // Pause button handler
        $container.off('click', '#pause-delay-btn').on('click', '#pause-delay-btn', function (e) {
            e.preventDefault();
            paused = true;
            renderCountdown();
        });
        // See question (skip) button handler
        $container.off('click', '#skip-delay-btn').on('click', '#skip-delay-btn', function () {
            clearInterval(delayInterval);
            delayInterval = null;
            $countdownDiv.remove();
            $('.answer-btn').show();
        });
    } else {
        $('#delay-countdown').remove();
        $('.answer-btn').show();
    }
}
// --- Ensure timer is reset when fetching a new question or changing filters ---
function resetDelayCountdown() {
    if (delayInterval) {
        clearInterval(delayInterval);
        delayInterval = null;
    }
    $('#delay-countdown').remove();
}

// Render topics/subtopics as text-only, multi-selectable
function renderDropdownMenu($menu, items, selectedItems) {
    $menu.empty();
    items.forEach(item => {
        const isSelected = selectedItems.includes(item);
        $menu.append(
            `<li>
                        <div class="dropdown-item-checkbox${isSelected ? ' selected' : ''}" data-value="${item}" tabindex="0" role="option" aria-selected="${isSelected}">
                            ${item}
                        </div>
                    </li>`
        );
    });
}

function updateFilters() {
    resetDelayCountdown();
    const data = {
        module: currentSelections.module,
        topics: currentSelections.topics,
        subtopics: currentSelections.subtopics
    };

    $.ajax({
        url: '/get_filters',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function (response) {
            // Populate topics dropdown (text only, no checkboxes)
            const $topicMenu = $('#topic-dropdown-menu');
            renderDropdownMenu($topicMenu, response.topics, currentSelections.topics);
            $('#topic-dropdown').prop('disabled', !data.module || response.topics.length === 0);
            updateDropdownLabel($('#topic-dropdown'), currentSelections.topics, "Select Topic");

            // Populate subtopics dropdown (text only, no checkboxes)
            const $subtopicMenu = $('#subtopic-dropdown-menu');
            renderDropdownMenu($subtopicMenu, response.subtopics, currentSelections.subtopics);
            $('#subtopic-dropdown').prop('disabled', !data.module || response.subtopics.length === 0);
            updateDropdownLabel($('#subtopic-dropdown'), currentSelections.subtopics, "Select Subtopic");
        }
    });
}

// Prevent dropdown from closing when clicking inside the menu (topics/subtopics)
$(document).on('mousedown', '.dropdown-menu-multiselect', function (e) {
    e.stopPropagation();
});

// Prevent dropdown from closing when clicking on a dropdown item (topics/subtopics)
$(document).on('mousedown', '#topic-dropdown-menu .dropdown-item-checkbox, #subtopic-dropdown-menu .dropdown-item-checkbox', function (e) {
    e.stopPropagation();
});

// Make label click toggle selection and update, but do not close dropdown
$(document).on('click', '#topic-dropdown-menu .dropdown-item-checkbox', function (e) {
    e.stopPropagation();
    const value = $(this).data('value');
    const idx = currentSelections.topics.indexOf(value);
    if (idx === -1) {
        currentSelections.topics.push(value);
    } else {
        currentSelections.topics.splice(idx, 1);
    }
    updateFilters();
    getNewQuestion();
});

$(document).on('click', '#subtopic-dropdown-menu .dropdown-item-checkbox', function (e) {
    e.stopPropagation();
    const value = $(this).data('value');
    const idx = currentSelections.subtopics.indexOf(value);
    if (idx === -1) {
        currentSelections.subtopics.push(value);
    } else {
        currentSelections.subtopics.splice(idx, 1);
    }
    updateDropdownLabel($('#subtopic-dropdown'), currentSelections.subtopics, "Select Subtopic");
    updateFilters();
    getNewQuestion();
});


// Prevent dropdown from closing when clicking the dropdown menu itself
$(document).on('mousedown', '.dropdown-menu-multiselect', function (e) {
    e.stopPropagation();
});

// Helper to update dropdown button label
function updateDropdownLabel($dropdownBtn, selected, defaultLabel) {
    if (selected.length === 0) {
        $dropdownBtn.text(defaultLabel);
    } else if (selected.length === 1) {
        $dropdownBtn.text(selected[0]);
    } else {
        $dropdownBtn.text(selected.length + " selected");
    }
}

function getNewQuestion(specificQuestionId = null) {
    resetDelayCountdown();
    // Hide manual continue button on new question
    $('#manual-continue-btn-row').hide();
    const data = {
        module: currentSelections.module,
        topics: currentSelections.topics,
        subtopics: currentSelections.subtopics,
        tags: currentSelections.tags
    };

    if (specificQuestionId) {
        data.question_id = specificQuestionId;
    }

    if (!data.module) return;

    $.ajax({
        url: '/get_question',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function (response) {
            if (response.error) {
                $('#question-text').text(response.error);
                $('#answers-container .answer-btn').each(function () {
                    $(this).text('').prop('disabled', true).hide();
                });
                $('#pdfs-dropdown-list').empty();
                $('#pdfs-dropdown-container').hide();
                $('#new-question-btn').hide();
                currentQuestionToken = null;
                return;
            }

            // Store the token immediately
            currentQuestionToken = response.token;
            isAdmin = response.is_admin || false;
            currentQuestionId = response.question_id || null;

            // Update question display
            $('#question-text').text(response.question);
            $('#module-info').text(response.module);
            $('#topic-info').text(response.topic);
            $('#subtopic-info').text(response.subtopic);

            // Remove tags display
            // $('#tags-container').empty();
            // response.tags.forEach(tag => {
            //     $('#tags-container').append(`<span class="tag">${tag}</span>`);
            // });

            // Reset buttons state
            $('.answer-btn').removeClass('btn-success btn-danger disabled')
                .addClass('btn-primary')
                .prop('disabled', false)
                .show();

            // Update answers while maintaining order for edits
            let $existingButtons = $('.answer-btn:visible');
            let existingAnswers = [];
            // If this is a refresh after edit, get existing button order
            if (specificQuestionId) {
                $existingButtons.each(function () {
                    existingAnswers.push($(this).text());
                });
            }

            // === NEW: Store answer_ids for each button ===
            // response.answer_ids is an array of question IDs for each answer
            response.answers.forEach((answer, index) => {
                const $btn = $('.answer-btn').eq(index);
                let finalAnswer = answer;
                // For edited questions, try to maintain the same position
                if (specificQuestionId && existingAnswers.length > 0) {
                    if (existingAnswers[index] === finalAnswer) {
                        // Same position, no change needed
                    } else if (answer === response.answers[0]) {
                        const oldCorrectIndex = existingAnswers.indexOf(response.answers[0]);
                        if (oldCorrectIndex !== -1) {
                            finalAnswer = existingAnswers[index];
                        }
                    }
                }
                $btn.text(finalAnswer)
                    .data('question-id', response.answer_ids ? response.answer_ids[index] : currentQuestionId)
                    .removeClass('disabled btn-success btn-danger')
                    .addClass('btn-primary')
                    .prop('disabled', false)
                    .show()
                    .unwrap('.answer-row');
            });

            // Hide unused buttons
            $('.answer-btn').each(function (idx) {
                if (idx >= response.answers.length) {
                    $(this).hide();
                }
            });

            // Update edit buttons for admins
            $('.edit-answer-btn').remove();
            if (isAdmin) {
                $('.answer-btn:visible').each(function (idx) {
                    if (!$(this).parent().hasClass('answer-row')) {
                        $(this).wrap('<div class="d-flex align-items-center answer-row" style="gap:8px;"></div>');
                    }
                    if ($(this).siblings('.edit-answer-btn').length === 0) {
                        $(this).after(`<button class="btn btn-outline-warning edit-answer-btn" style="min-width:60px; font-size:1em; font-weight:500;" data-idx="${idx}">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-pencil-square" viewBox="0 0 16 16">
                                        <path d="M15.502 1.94a.5.5 0 0 1 0 .706L14.459 3.69l-2-2L13.502.646a.5.5 0 0 1 .707 0l1.293 1.293zm-1.75 2.456-2-2L4.939 9.21a.5.5 0 0 0-.121.196l-.805 2.414a.25.25 0 0 0 .316.316l2.414-.805a.5.5 0 0 0 .196-.12l6.813-6.814z"/>
                                        <path fill-rule="evenodd" d="M1 13.5A1.5 1.5 0 0 0 2.5 15h11a 1.5 1.5 0 0 0 1.5-1.5v-11A1.5 1.5 0 0 0 13.5 1h-11A1.5 1.5 0 0 0 1 2.5v11zm1.5-.5a.5.5 0 0 1-.5-.5v-11a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 .5.5v11a.5.5 0 0 1-.5.5h-11z"/>
                                    </svg> Edit</button>`);
                    }
                });
            }

            $('#new-question-btn').hide();

            // Update PDFs and tags
            $('#tags-container').empty();
            response.tags.forEach(tag => {
                $('#tags-container').append(`<span class="tag">${tag}</span>`);
            });

            $('#pdfs-dropdown-list').empty();
            if (response.pdfs && response.pdfs.length > 0) {
                // Store the current question ID on the dropdown button
                $('#pdfsDropdown').attr('data-question-id', response.question_id);

                // Update button text to show PDF count
                $('#pdfsDropdown').text(`Relevant Lecture Notes (${response.pdfs.length})`);

                // Add PDFs to dropdown with match percentages
                response.pdfs.forEach(pdf => {
                    let name = pdf.name || pdf;
                    let url = pdf.path || pdf;
                    if (!/^https?:\/\//.test(url)) {
                        url = '/pdf/' + url.replace(/^\/*/, '');
                    }

                    // Create display text with metadata and match percentage
                    let displayText = name;
                    let metadataText = '';

                    if (pdf.module) {
                        metadataText += pdf.module;
                        if (pdf.topic) {
                            metadataText += ` > ${pdf.topic}`;
                            if (pdf.subtopic) {
                                metadataText += ` > ${pdf.subtopic}`;
                            }
                        }
                    }

                    // Determine match class based on percentage
                    let matchClass = '';
                    if (pdf.match_percent >= 85) {
                        matchClass = 'match-high';
                    } else if (pdf.match_percent >= 50) {
                        matchClass = 'match-medium';
                    } else {
                        matchClass = 'match-low';
                    }

                    // Create match percentage pill
                    let matchPill = `<span class="match-pill ${matchClass}">${pdf.match_percent}% match</span>`;

                    if (metadataText) {
                        displayText = `${name} ${matchPill}<br><small class="text-muted">${metadataText}</small>`;
                    } else {
                        displayText = `${name} ${matchPill}`;
                    }

                    $('#pdfs-dropdown-list').append(`<li><a class="dropdown-item" href="${url}" target="_blank">${displayText}</a></li>`);
                });
                $('#pdfs-dropdown-container').show();
            } else {
                // No PDFs found initially - still show the dropdown button for on-demand loading
                $('#pdfsDropdown').attr('data-question-id', response.question_id);
                $('#pdfsDropdown').text('Find Lecture Notes');
                $('#pdfs-dropdown-container').show();
            }

            // --- Delay showing answers if needed ---
            showAnswerButtonsWithDelay();
            // Do NOT hide manual continue button here, only hide on new question fetch
            // $('#manual-continue-btn-row').hide(); // <-- REMOVE this line if present
        }
    });
}

// --- Answer button logic ---
$(document).off('click', '.answer-btn').on('click', '.answer-btn', function () {
    const $btn = $(this);
    if ($btn.prop('disabled')) return;
    const selectedAnswer = $btn.text();
    updateManualContinueState(); // <-- Ensure manualContinue is up-to-date before using
    // Send the token with the answer
    $.ajax({
        url: '/check_answer',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            answer: selectedAnswer,
            token: currentQuestionToken
        }),
        success: function (response) {
            if (response.correct) {
                $btn.removeClass('btn-primary').addClass('btn-success');
                $('.answer-btn').prop('disabled', true);
                if (manualContinue) {
                    // Show manual continue button
                    $('#manual-continue-btn-row').show();
                } else {
                    // Auto-advance after 1 second
                    setTimeout(function () {
                        getNewQuestion();
                    }, 1000);
                }
            } else {
                // Only disable and mark the clicked button as incorrect
                $btn.removeClass('btn-primary').addClass('btn-danger disabled').prop('disabled', true);
                // Let other buttons remain clickable for more attempts
            }
        },
        error: function (xhr) {
            if (xhr.status === 401) {
                window.location.href = "{{ url_for('login') }}";
            }
        }
    });
});

// Manual continue button handler
$(document).off('click', '#manual-continue-btn').on('click', '#manual-continue-btn', function () {
    $('#manual-continue-btn-row').hide();
    getNewQuestion();
});

// --- Edit answer button logic (admin only) ---
function cleanupEditForms() {
    $('.edit-answer-form').each(function () {
        const $form = $(this);
        const $row = $form.closest('.answer-row');
        $row.find('.answer-btn').show();
        $row.find('.edit-answer-btn').show();
        $form.remove();
    });
    // Re-enable all buttons
    $('.edit-answer-btn, .answer-btn').each(function () {
        const $btn = $(this);
        if (!$btn.hasClass('btn-danger')) {
            $btn.prop('disabled', false);
        }
    });
}

$(document).off('click', '.edit-answer-btn').on('click', '.edit-answer-btn', function (e) {
    e.preventDefault();

    // First cleanup any existing edit forms
    cleanupEditForms();

    const idx = $(this).data('idx');
    const $answerBtn = $('.answer-btn').eq(idx);
    const $editBtn = $(this);
    const currentText = $answerBtn.text();

    // Disable all edit and answer buttons while editing
    $('.edit-answer-btn, .answer-btn').prop('disabled', true);

    // Show the edit form
    $answerBtn.hide();
    $editBtn.hide();
    const formHtml = `
                <form class="edit-answer-form d-flex align-items-center w-100" style="gap:8px;">
                    <input type="text" class="form-control form-control-sm" value="${currentText}" style="flex:1; min-width:120px;">
                    <button type="submit" class="btn btn-success btn-sm">Save</button>
                    <button type="button" class="btn btn-secondary btn-sm cancel-edit-btn">Cancel</button>
                </form>
            `;
    $editBtn.after(formHtml);

    // Focus the input field
    $editBtn.siblings('.edit-answer-form').find('input').focus();
});
// Save edited answer
$(document).off('submit', '.edit-answer-form').on('submit', '.edit-answer-form', function (e) {
    e.preventDefault();
    const $form = $(this);
    const $submitBtn = $form.find('button[type="submit"]');
    const $cancelBtn = $form.find('.cancel-edit-btn');
    // Disable form buttons and show loading state
    $submitBtn.prop('disabled', true);
    $cancelBtn.prop('disabled', true);
    $submitBtn.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...');
    const $answerBtn = $form.closest('.answer-row').find('.answer-btn');
    const questionId = $answerBtn.data('question-id'); // Use the button's question ID
    const newText = $form.find('input').val();
    $.ajax({
        url: '/edit_answer',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            question_id: questionId, // Use the correct question ID
            new_text: newText
        }),
        success: function (resp) {
            if (resp.success) {
                cleanupEditForms();
                getNewQuestion(currentQuestionId);
            } else {
                alert('Failed to update answer.');
                $submitBtn.prop('disabled', false);
                $cancelBtn.prop('disabled', false);
                $submitBtn.html('Save');
                $('.edit-answer-btn').prop('disabled', false);
            }
        },
        error: function () {
            alert('Error updating answer.');
            $submitBtn.prop('disabled', false);
            $cancelBtn.prop('disabled', false);
            $submitBtn.html('Save');
            $('.edit-answer-btn').prop('disabled', false);
        }
    });
});
// Cancel edit
$(document).off('click', '.cancel-edit-btn').on('click', '.cancel-edit-btn', function () {
    cleanupEditForms();
});

$('#new-question-btn').off('click').on('click', function () {
    getNewQuestion();
});

// Report Question button always visible
$('#report-question-btn').off('click').on('click', function () {
    const questionText = $('#question-text').text();
    let answerText = '';
    // Try to get the correct answer (if already answered correctly)
    $('.answer-btn').each(function () {
        if ($(this).hasClass('btn-success')) answerText = $(this).text();
    });
    // If not found, just use the first answer button's text
    if (!answerText) answerText = $('.answer-btn').first().text();

    // Get distractor IDs from answer buttons' data attributes
    let distractorIds = [];
    $('.answer-btn:visible').each(function () {
        const questionId = $(this).data('question-id');
        if (questionId) {
            distractorIds.push(questionId);
        }
    });

    if (questionText) {
        window.location.href = '/report_question?question=' + encodeURIComponent(questionText) +
            '&answer=' + encodeURIComponent(answerText) +
            '&distractor_ids=' + encodeURIComponent(distractorIds.join(','));
        console.log("Redirecting to report page with distractor IDs:", distractorIds.join(','));
    }
});

// --- Module dropdown logic (single select, styled like topics) ---
function updateModuleDropdownLabel() {
    const $btn = $('#module-dropdown');
    if (!currentSelections.module) {
        $btn.text('Select Module');
    } else {
        $btn.text(currentSelections.module);
    }
}
function updateModuleDropdownSelection() {
    $('#module-dropdown-menu .dropdown-item-module').each(function () {
        const val = $(this).data('value');
        if (val === currentSelections.module) {
            $(this).addClass('selected').attr('aria-selected', 'true');
        } else {
            $(this).removeClass('selected').attr('aria-selected', 'false');
        }
    });
}
$(document).on('click', '#module-dropdown-menu .dropdown-item-module', function (e) {
    const value = $(this).data('value');
    if (currentSelections.module === value) {
        currentSelections.module = '';
    } else {
        currentSelections.module = value;
    }
    currentSelections.topics = [];
    currentSelections.subtopics = [];
    updateModuleDropdownLabel();
    updateModuleDropdownSelection();
    updateFilters();

    // Show/hide welcome and QA sections
    if (currentSelections.module) {
        $('#welcome-section').hide();
        $('#qa-section').show();
        getNewQuestion();
    } else {
        $('#qa-section').hide();
        $('#welcome-section').show();
    }
});
// Prevent dropdown from closing on selection
$(document).on('mousedown', '#module-dropdown-menu .dropdown-item-module', function (e) {
    e.preventDefault();
});
// Update label and selection on show
$('#module-dropdown').on('show.bs.dropdown', function () {
    updateModuleDropdownLabel();
    updateModuleDropdownSelection();
});
// Also update on page load
$(document).ready(function () {
    updateModuleDropdownLabel();
    updateModuleDropdownSelection();
});

// --- Remove old <select> module logic ---
// $('#module-select').change(function() { ... }); // REMOVE

// Update filters and UI if module is set from URL
$(document).ready(function () {
    const urlParams = new URLSearchParams(window.location.search);
    if (window.FLASHCARDS_CONFIG.session_user_id) {
        if (urlParams.has('module')) {
            currentSelections.module = urlParams.get('module');
            updateModuleDropdownLabel();
            updateModuleDropdownSelection();
            updateFilters();
            $('#welcome-section').hide();
            $('#qa-section').show();
            getNewQuestion();
        } else {
            $('#qa-section').hide();
            $('#welcome-section').show();
        }
    } else {
        $('#qa-section').hide();
        $('#welcome-section').show();
    }
});

// Add click handlers to close dropdowns when clicking outside
$(document).on('click', function (e) {
    if (!$(e.target).closest('#topic-dropdown-menu').length &&
        !$(e.target).closest('#topic-dropdown').length) {
        $('#topic-dropdown').dropdown('hide');
    }
    if (!$(e.target).closest('#subtopic-dropdown-menu').length &&
        !$(e.target).closest('#subtopic-dropdown').length) {
        $('#subtopic-dropdown').dropdown('hide');
    }
});

// Remove any existing click handlers that might interfere
$('.dropdown-menu-multiselect').off('mousedown');

// Stripe widget functionality
$(document).ready(function () {
    const $stripeWidget = $('#stripe-widget');

    // Check if user has chosen to never show the widget again
    if (localStorage.getItem('never-show-payment-widget') === 'true') {
        $stripeWidget.remove();
        return; // Exit early, don't initialize the widget
    }

    // Only now fully remove the preload-hidden class to prevent flashing
    $stripeWidget.removeClass('preload-hidden');

    // Only initialize if the widget exists on the page
    if ($stripeWidget.length) {
        const $stripeToggleBtn = $('#stripe-toggle-btn');
        const $stripeCloseBtn = $('#stripe-close-btn');
        const $stripeHeader = $('#stripe-header');
        const $supportLink = $('#support-link');
        const $neverShowBtn = $('#never-show-widget-btn');
        let selectedAmount = 1; // Default amount

        // Handle "Do not show again" button click
        $neverShowBtn.on('click', function () {
            localStorage.setItem('never-show-payment-widget', 'true');
            $stripeWidget.fadeOut(300, function () {
                $stripeWidget.remove();
            });
        });

        // Stripe initialization
        const stripe = Stripe(window.FLASHCARDS_CONFIG.stripe_publishable_key);

        // Check if widget was dismissed in this session
        if (sessionStorage.getItem('stripe-widget-dismissed') === 'true') {
            $stripeWidget.hide();
        }

        // Toggle widget expanded/minimized state
        function toggleStripeWidget() {
            $stripeWidget.toggleClass('minimized');

            // Update the toggle button icon
            if ($stripeWidget.hasClass('minimized')) {
                $stripeToggleBtn.html('▲');
            } else {
                $stripeToggleBtn.html('▼');
            }
        }

        // Close widget and remember for this session only
        $stripeCloseBtn.click(function (e) {
            e.stopPropagation();
            $stripeWidget.hide();
            sessionStorage.setItem('stripe-widget-dismissed', 'true');
        });

        // Toggle on header click
        $stripeHeader.click(function () {
            toggleStripeWidget();
        });

        // Prevent the toggle from triggering the header click
        $stripeToggleBtn.click(function (e) {
            e.stopPropagation();
            toggleStripeWidget();
        });

        // Re-show widget when footer link is clicked
        $supportLink.click(function (e) {
            e.preventDefault();
            $stripeWidget.show();

            // If it was minimized, expand it
            if ($stripeWidget.hasClass('minimized')) {
                toggleStripeWidget();
            }

            // Clear the dismissed state
            sessionStorage.removeItem('stripe-widget-dismissed');
        });

        // Amount option selection
        $('.amount-option').click(function () {
            $('.amount-option').removeClass('selected');
            $(this).addClass('selected');
            selectedAmount = $(this).data('amount');
            $('#custom-amount').val(''); // Clear custom amount
        });

        // Custom amount input handling - FIX: Properly track custom amount
        $('#custom-amount').on('input', function () {
            const customAmount = parseInt($(this).val());
            if (customAmount && customAmount > 0) {
                // When valid custom amount is entered, deselect preset amounts
                $('.amount-option').removeClass('selected');
                selectedAmount = customAmount;
            } else if ($('.amount-option.selected').length) {
                // If invalid and a preset is selected, use that
                selectedAmount = $('.amount-option.selected').data('amount');
            } else {
                // Default to £1 if nothing is selected and custom is invalid
                $('.amount-option[data-amount="1"]').addClass('selected');
                selectedAmount = 1;
            }
        });

        // Checkout button - FIX: Always check for custom amount value first
        $('#checkout-button').click(function () {
            const button = $(this);
            button.prop('disabled', true).text('Processing...');

            let finalAmount = selectedAmount; // Start with currently selected amount

            // Check if there's a valid custom amount entered (this takes priority)
            const customAmountInput = $('#custom-amount').val().trim();
            if (customAmountInput) {
                const customAmount = parseInt(customAmountInput);
                if (customAmount && customAmount > 0) {
                    finalAmount = customAmount;
                    console.log('Using custom amount for checkout:', finalAmount);
                }
            }

            // Ensure we have a valid amount (minimum £1)
            finalAmount = Math.max(1, finalAmount);

            // Create a checkout session on your server with the final amount
            $.ajax({
                url: '/create-checkout-session',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ amount: finalAmount }),
                success: function (response) {
                    // Redirect to Stripe Checkout
                    stripe.redirectToCheckout({ sessionId: response.id })
                        .then(function (result) {
                            if (result.error) {
                                console.error('Stripe checkout error:', result.error);
                                alert(result.error.message);
                                button.prop('disabled', false).text('Support Now');
                            }
                        });
                },
                error: function (xhr) {
                    console.error('Error creating checkout session');

                    // Try to parse detailed error message
                    let errorMessage = 'Sorry, there was a problem processing your request. Please try again later.';

                    try {
                        if (xhr.responseJSON && xhr.responseJSON.error) {
                            errorMessage = xhr.responseJSON.error;
                            console.error('Detailed error:', errorMessage);
                        }
                    } catch (e) {
                        console.error('Could not parse error response:', e);
                    }

                    alert(errorMessage);
                    button.prop('disabled', false).text('Support Now');
                }
            });
        });

        // Minimize the widget when answer buttons appear
        const originalGetNewQuestion = window.getNewQuestion;
        window.getNewQuestion = function (...args) {
            originalGetNewQuestion.apply(this, args);

            // Minimize widget when there are answer options
            setTimeout(function () {
                if ($('.answer-btn:visible').length > 0 && !$stripeWidget.hasClass('minimized')) {
                    $stripeWidget.addClass('minimized');
                    $stripeToggleBtn.html('▲');
                }
            }, 300);
        };

        // Also minimize when a module is selected (as that triggers answers to appear)
        $(document).on('click', '#module-dropdown-menu .dropdown-item-module', function () {
            setTimeout(function () {
                if ($('#qa-section:visible').length > 0 && !$stripeWidget.hasClass('minimized')) {
                    $stripeWidget.addClass('minimized');
                    $stripeToggleBtn.html('▲');
                }
            }, 300);
        });
    }
});

// --- Manual continue state with toggle button ---
let manualContinue = false;
function setManualContinueUI(state) {
    manualContinue = !!state;
    localStorage.setItem('manualContinue', manualContinue ? 'true' : 'false');
    const $btn = $('#manual-continue-toggle');
    if (manualContinue) {
        $btn.addClass('active');
    } else {
        $btn.removeClass('active');
    }
}
function updateManualContinueState() {
    // Always sync manualContinue with UI state
    manualContinue = $('#manual-continue-toggle').hasClass('active');
}
$(document).ready(function () {
    setManualContinueUI(localStorage.getItem('manualContinue') === 'true');
    // Attach click handler for toggle button
    $('#manual-continue-toggle').off('click').on('click', function () {
        setManualContinueUI(!manualContinue);
    });
});