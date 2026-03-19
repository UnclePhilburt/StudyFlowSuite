// Content script - runs on every webpage to detect quiz questions
console.log('StudyFlowSuite loaded on:', window.location.href);

// Check if we're inside a Learnosity iframe or Canvas LTI launch page
const isLearnosity = window.location.hostname.includes('learnosity.com');
const isCanvasLTI = window.location.hostname.includes('quiz-lti') || window.location.pathname.includes('/lti/launch');

if (isLearnosity) {
  console.log('🎓 Running inside Learnosity iframe!');
}

// CRITICAL: Don't interfere with LTI security handshake on Canvas quiz pages
if (isCanvasLTI && window.location.pathname.includes('/lti/launch')) {
  console.log('⏸️ Detected LTI launch page - pausing extension to avoid 403 error');
  console.log('⏸️ Extension will activate after page redirect completes');
  // Don't initialize anything - just exit and let the security handshake complete
  // The extension will reinitialize when the actual quiz page loads
}

// Load custom selectors for this domain into window object (for synchronous access)
(async function loadCustomSelectors() {
  const domain = window.location.hostname;
  const storage = await chrome.storage.local.get('customSelectors');
  if (storage.customSelectors && storage.customSelectors[domain]) {
    window.studyflowCustomSelectors = storage.customSelectors[domain];
    console.log('📋 Loaded custom selectors for', domain);
  }
})();

// Only initialize if not on LTI launch page (to avoid 403 errors)
if (isCanvasLTI && window.location.pathname.includes('/lti/launch')) {
  // Skip all initialization - just wait for redirect
  console.log('⏸️ Skipping initialization on LTI launch page');
} else if (isLearnosity || isCanvasLTI) {
  // For Learnosity/Canvas LTI pages, wait for page to fully load and initialize
  console.log('⏳ Waiting 3 seconds for Learnosity to initialize...');
  setTimeout(() => {
    initializeExtension();
  }, 3000); // Wait 3 seconds for Learnosity's security to finish loading
} else {
  // Safe to initialize immediately - not a sensitive page
  initializeExtension();
}

function initializeExtension() {
  console.log('✅ Initializing StudyFlowSuite extension');

// Track answered questions on one-page quizzes
let answeredQuestions = new Set();

// Track answered Learnosity questions (by question text hash)
let answeredLearnosityQuestions = new Set();

// Detect one-page quiz (all questions visible at once)
function detectOnePageQuiz() {
  console.log('🔍 Scanning for unanswered question in one-page quiz...');

  // Check if this is a Learnosity/Canvas quiz (most common case)
  const isLearnosity = window.location.href.includes('learnosity') ||
                      window.location.href.includes('canvas') ||
                      document.querySelector('[data-automation^="sdk-"]');

  if (isLearnosity) {
    console.log('📚 Learnosity/Canvas one-page quiz detected');
    console.log('   All questions are visible on the same page - finding unanswered questions...');

    // Find ALL question containers on the page
    // Try multiple selectors to find question containers
    let questionContainers = document.querySelectorAll('[data-automation="sdk-take-item-question"]');

    if (questionContainers.length === 0) {
      // Fallback: try other Learnosity selectors
      questionContainers = document.querySelectorAll('.lrn-assess-item, .lrn_widget, [class*="lrn_question"]');
    }

    console.log(`   Found ${questionContainers.length} total question container(s) on page`);
    console.log(`   Already answered: ${answeredLearnosityQuestions.size} questions`);

    if (questionContainers.length === 0) {
      console.log('   No question containers found, falling back to regular detectQuiz()');
      console.log('   Current URL:', window.location.href);
      console.log('   Checking if regular detectQuiz() can find anything...');
      const regularResult = detectQuiz();
      console.log('   Regular detectQuiz() result:', regularResult.found ? 'FOUND' : 'NOT FOUND');
      if (regularResult.found) {
        console.log('   Found question:', regularResult.question.substring(0, 50));
      }
      return regularResult;
    }

    // Iterate through ALL containers to find first unanswered one
    for (let i = 0; i < questionContainers.length; i++) {
      const container = questionContainers[i];

      // Skip if container is not visible
      if (container.offsetParent === null || container.offsetHeight === 0) {
        console.log(`   Container ${i+1}/${questionContainers.length}: Hidden, skipping`);
        continue;
      }

      // Get question text
      let questionText = '';
      const questionTextEl = container.querySelector('.user_content > p, .user_content, .lrn_stimulus, [class*="question"]');
      if (questionTextEl) {
        questionText = questionTextEl.textContent.trim();
      } else {
        // Fallback: get text from container
        questionText = container.textContent.trim().split('\n')[0];
      }

      if (!questionText || questionText.length < 5) {
        console.log(`   Container ${i+1}/${questionContainers.length}: No question text found`);
        continue;
      }

      const questionHash = questionText.substring(0, 200);

      // Check if already answered
      if (answeredLearnosityQuestions.has(questionHash)) {
        console.log(`   Container ${i+1}/${questionContainers.length}: Already answered - "${questionText.substring(0, 30)}..."`);
        continue;
      }

      console.log(`   Container ${i+1}/${questionContainers.length}: Found UNANSWERED question - "${questionText.substring(0, 50)}..."`);

      // Find input elements - check ALL possible locations
      const radioInputs = container.querySelectorAll('input[type="radio"], input[type="checkbox"]');
      const textInputs = container.querySelectorAll('textarea, input[type="text"]');

      // Also check for iframes (rich text editors)
      const iframes = container.querySelectorAll('iframe');

      // Also check for contenteditable divs (some rich text editors)
      const contentEditables = container.querySelectorAll('[contenteditable="true"]');

      console.log(`      → Found in container: ${radioInputs.length} radio, ${textInputs.length} textareas, ${iframes.length} iframes, ${contentEditables.length} contenteditable`);

      // Filter to visible only
      const visibleRadios = Array.from(radioInputs).filter(input =>
        input.offsetParent !== null && input.getAttribute('aria-hidden') !== 'true'
      );
      const visibleTextInputs = Array.from(textInputs).filter(input =>
        input.offsetParent !== null && input.getAttribute('aria-hidden') !== 'true'
      );

      const visibleIframes = Array.from(iframes).filter(iframe =>
        iframe.offsetParent !== null && iframe.offsetHeight > 0
      );

      const visibleContentEditables = Array.from(contentEditables).filter(el =>
        el.offsetParent !== null && el.offsetHeight > 0
      );

      console.log(`      → Visible: ${visibleRadios.length} radio/checkbox, ${visibleTextInputs.length} text inputs, ${visibleIframes.length} iframes, ${visibleContentEditables.length} contenteditable`);

      // Check if multiple choice (priority)
      if (visibleRadios.length > 0) {
        // Determine if this is a multiple-answer question (checkboxes) or single-answer (radio)
        const isMultipleAnswer = visibleRadios[0].type === 'checkbox';

        // Check if already answered
        const isAnswered = visibleRadios.some(input => input.checked);
        if (isAnswered) {
          console.log(`      → Already answered (${isMultipleAnswer ? 'checkbox' : 'radio'} checked), marking as answered`);
          answeredLearnosityQuestions.add(questionHash);
          continue;
        }

        // DO NOT mark as answered yet - will be marked after clicking succeeds

        // Get answers
        const answers = [];
        const radioGroupId = `studyflow-radio-${Date.now()}`;

        visibleRadios.forEach((input, index) => {
          input.setAttribute('data-studyflow-radio-group', radioGroupId);
          input.setAttribute('data-studyflow-radio-index', index);

          // Find label text
          let answerText = '';
          if (input.id) {
            const label = document.querySelector(`label[for="${input.id}"]`);
            if (label) answerText = label.textContent.trim();
          }
          if (!answerText) {
            const parentLabel = input.closest('label');
            if (parentLabel) answerText = parentLabel.textContent.trim();
          }
          if (!answerText && input.parentElement) {
            answerText = input.parentElement.textContent.trim();
          }

          if (answerText) {
            answers.push({
              index: index + 1,
              text: answerText.replace(/\s+/g, ' ').trim(),
              element: input,
              type: input.type
            });
          }
        });

        console.log(`      → Returning ${isMultipleAnswer ? 'MULTIPLE-ANSWER' : 'single-answer'} question with ${answers.length} options`);
        return {
          question: questionText,
          answers: answers,
          found: true,
          questionHash: questionHash,
          isEssay: false,
          isMultipleAnswer: isMultipleAnswer,
          radioGroupId: radioGroupId,
          questionElement: container,
          debug: [`One-page: ${isMultipleAnswer ? 'multiple-answer checkbox' : 'single-answer radio'}`]
        };
      }

      // Check if essay/text question (textarea or iframe)
      if (visibleTextInputs.length > 0 || visibleIframes.length > 0) {
        // Prefer visible text inputs first
        if (visibleTextInputs.length > 0) {
          const field = visibleTextInputs[0];

          // Check if already filled
          if (field.value.trim() !== '') {
            console.log(`      → Already answered (text filled), marking as answered`);
            answeredLearnosityQuestions.add(questionHash);
            continue;
          }

          // DO NOT mark as answered yet - will be marked after filling succeeds

          const fieldId = `studyflow-field-${Date.now()}`;
          field.setAttribute('data-studyflow-field-id', fieldId);

          console.log(`      → Returning essay/text question (textarea)`);
          return {
            question: questionText,
            answers: [],
            found: true,
            isEssay: true,
            essayFieldId: fieldId,
            isRichTextEditor: field.tagName === 'TEXTAREA',
            questionElement: container,
            questionHash: questionHash,
            debug: ['One-page: essay/text']
          };
        }

        // If no visible text inputs, check for iframe (rich text editor)
        if (visibleIframes.length > 0) {
          const iframe = visibleIframes[0];

          // Check if iframe has content (already filled)
          try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            const iframeBody = iframeDoc.body;
            if (iframeBody && iframeBody.textContent.trim().length > 0) {
              console.log(`      → Already answered (iframe filled), marking as answered`);
              answeredLearnosityQuestions.add(questionHash);
              continue;
            }
          } catch (e) {
            // Cross-origin iframe - can't check content, assume empty
            console.log(`      → Cannot access iframe content (cross-origin), assuming empty`);
          }

          // DO NOT mark as answered yet - will be marked after filling succeeds

          // Mark iframe with ID
          const fieldId = `studyflow-field-${Date.now()}`;
          iframe.setAttribute('data-studyflow-field-id', fieldId);

          console.log(`      → Returning essay question (rich text editor iframe)`);
          return {
            question: questionText,
            answers: [],
            found: true,
            isEssay: true,
            essayFieldId: fieldId,
            isRichTextEditor: true,
            questionElement: container,
            questionHash: questionHash,
            debug: ['One-page: essay/rich text editor']
          };
        }
      }

      console.log(`      → No answerable inputs found, skipping`);
    }

    // No more unanswered questions
    console.log('   ✅ All questions answered! Ready for final submit');
    return {
      question: null,
      answers: [],
      found: false,
      debug: ['One-page: all questions completed']
    };
  }

  // Generic one-page quiz detection (for other platforms)
  console.log('📄 Generic one-page quiz - scanning for question containers...');

  // Find all question containers
  const questionContainers = document.querySelectorAll('.question, [class*="question"]');

  for (const container of questionContainers) {
    // Skip if container is not visible
    if (container.offsetParent === null || container.offsetHeight === 0 || container.offsetWidth === 0) {
      console.log('⏭️ Skipping hidden question container');
      continue;
    }

    // Create a unique question ID
    const questionId = container.getAttribute('data-question-id') || container.textContent.substring(0, 100);

    // Skip if we've already processed this question in this session
    if (answeredQuestions.has(questionId)) {
      console.log('⏭️ Skipping already answered question');
      continue;
    }

    // Find the question text within this container
    const questionTextElement = container.querySelector('.question_text, .question-text, .questionText, .qtext, [class*="question_text"]');
    let questionText = '';

    if (questionTextElement) {
      questionText = questionTextElement.textContent.trim();
    } else {
      // Fallback: try to find the question text from common patterns
      const fallbackElement = container.querySelector('strong, b, h3, h4, h5, p');
      if (fallbackElement) {
        questionText = fallbackElement.textContent.trim();
      } else {
        // Last resort: get first substantial text from container
        questionText = container.textContent.trim().split('\n').find(line => line.length > 10) || '';
      }
    }

    if (!questionText || questionText.length < 10) continue;

    // Check if it's an essay/text question
    const textInputs = container.querySelectorAll('textarea, input[type="text"]');
    if (textInputs.length > 0) {
      for (const field of textInputs) {
        if (field.offsetParent !== null) {
          // Skip if field already has a value (don't add to answeredQuestions - just skip this field)
          if (field.value.trim() !== '') {
            console.log('⏭️ Text field already filled, skipping without tracking');
            continue; // Skip to next field
          }

          // Found unanswered text question
          console.log('✅ Found unanswered TEXT question:', questionText.substring(0, 100));

          // Mark the field with a unique identifier
          const fieldId = `studyflow-field-${Date.now()}`;
          field.setAttribute('data-studyflow-field-id', fieldId);

          // Mark as answered (will be filled)
          container.setAttribute('data-question-id', questionId);
          answeredQuestions.add(questionId);

          return {
            question: questionText,
            answers: [],
            found: true,
            isEssay: true,
            essayFieldId: fieldId,
            questionElement: container,
            debug: ['One-page quiz: text question']
          };
        }
      }
    }

    // Check if it's a multiple choice question
    const radioInputs = container.querySelectorAll('input[type="radio"], input[type="checkbox"]');
    if (radioInputs.length > 0) {
      // Check if any answer is already selected (don't add to answeredQuestions - just skip this question)
      const isAnswered = Array.from(radioInputs).some(input => input.checked);
      if (isAnswered) {
        console.log('⏭️ Radio button already checked, skipping without tracking');
        continue;
      }

      // Found unanswered multiple choice question
      console.log('✅ Found unanswered MULTIPLE CHOICE question:', questionText.substring(0, 100));

      const answers = [];
      const radioGroupId = `studyflow-radio-${Date.now()}`;

      radioInputs.forEach((input, index) => {
        // Mark each input with a unique group identifier
        input.setAttribute('data-studyflow-radio-group', radioGroupId);
        input.setAttribute('data-studyflow-radio-index', index);

        // Find label text
        let answerText = '';
        if (input.id) {
          const label = container.querySelector(`label[for="${input.id}"]`);
          if (label) answerText = label.textContent.trim();
        }
        if (!answerText) {
          const parentLabel = input.closest('label');
          if (parentLabel) answerText = parentLabel.textContent.trim();
        }
        if (!answerText && input.nextSibling) {
          answerText = input.nextSibling.textContent?.trim() || '';
        }
        if (!answerText) {
          const parent = input.parentElement;
          if (parent) answerText = parent.textContent.trim();
        }

        answerText = answerText.replace(/\s+/g, ' ').trim();

        if (answerText && answerText.length > 0) {
          answers.push({
            index: index + 1,
            text: answerText,
            element: input,
            type: input.type
          });
        }
      });

      // Mark as answered (will be clicked)
      container.setAttribute('data-question-id', questionId);
      answeredQuestions.add(questionId);

      return {
        question: questionText,
        answers: answers,
        found: true,
        isEssay: false,
        radioGroupId: radioGroupId,
        questionElement: container,
        debug: ['One-page quiz: multiple choice']
      };
    }
  }

  // No more unanswered questions found
  console.log('✅ All questions answered!');
  return {
    question: null,
    answers: [],
    found: false,
    debug: ['One-page quiz: all questions completed']
  };
}

// Detect quiz questions on the page
function detectQuiz() {
  const quizData = {
    question: null,
    answers: [],
    found: false,
    debug: [],
    isEssay: false,
    essayField: null,
    questionElement: null // Store reference to question element
  };

  console.log('=== QUIZ DETECTION DEBUG ===');
  console.log('URL:', window.location.href);
  console.log('Domain:', window.location.hostname);

  // LEARNOSITY: Check for question type label first (makes detection more accurate)
  const questionTypeElement = document.querySelector('[data-automation="sdk-interaction-type-name-div"]');
  let detectedQuestionType = null;
  if (questionTypeElement) {
    const typeText = questionTypeElement.textContent.trim();
    detectedQuestionType = typeText; // "Multiple Choice", "Essay", "Fill in the Blank", "True/False", etc.
    console.log(`🎯 Detected question type from label: "${detectedQuestionType}"`);
    quizData.debug.push(`Detected question type: ${detectedQuestionType}`);
  }

  // Check for custom selectors first (synchronously stored in window object)
  if (window.studyflowCustomSelectors) {
    const customSelectors = window.studyflowCustomSelectors;
    console.log('🎯 Using custom selectors for this site:', customSelectors);

    // Find question using custom selector
    const questionEl = document.querySelector(customSelectors.question);
    if (questionEl) {
      quizData.question = questionEl.textContent.trim();
      quizData.found = true;
      quizData.debug.push('Found question using custom selector');
      console.log('✅ Found question using custom selector:', quizData.question.substring(0, 100));
    }

    // Find answers using custom selector
    const answersContainer = document.querySelector(customSelectors.answers);
    if (answersContainer) {
      const answerInputs = answersContainer.querySelectorAll('input[type="radio"], input[type="checkbox"]');
      console.log(`Found ${answerInputs.length} answer inputs in custom container`);

      answerInputs.forEach((input, index) => {
        let answerText = '';

        // Try to find label
        if (input.id) {
          const label = document.querySelector(`label[for="${input.id}"]`);
          if (label) answerText = label.textContent.trim();
        }
        if (!answerText) {
          const parentLabel = input.closest('label');
          if (parentLabel) answerText = parentLabel.textContent.trim();
        }
        if (!answerText) {
          const parent = input.parentElement;
          if (parent) answerText = parent.textContent.trim();
        }

        if (answerText) {
          quizData.answers.push({
            index: index + 1,
            text: answerText.replace(/\s+/g, ' ').trim(),
            element: input,
            type: input.type
          });
        }
      });

      console.log(`✅ Found ${quizData.answers.length} answers using custom selector`);
    }

    // Return if we found both question and answers
    if (quizData.found && quizData.answers.length > 0) {
      return quizData;
    }
  }

  // Log all elements with data-automation attributes (Learnosity specific)
  const allDataAutomation = document.querySelectorAll('[data-automation]');
  console.log(`Found ${allDataAutomation.length} elements with data-automation attributes`);
  if (allDataAutomation.length > 0 && allDataAutomation.length < 20) {
    allDataAutomation.forEach(el => {
      console.log(`  - data-automation="${el.getAttribute('data-automation')}" (${el.tagName})`);
    });
  }

  // Check if this is Colibri Real Estate
  const isColibri = window.location.hostname.includes('colibri');
  if (isColibri) {
    console.log('🎓 Colibri Real Estate detected!');
    // Check for iframes (Colibri uses iframe-based quizzes)
    const iframes = document.querySelectorAll('iframe.resp-iframe, .form-wrap iframe');
    if (iframes.length > 0) {
      console.log(`Found ${iframes.length} quiz iframe(s)`);
      console.log('⚠️ Note: Extension may need to run inside the iframe. Make sure the quiz content is loaded.');
    }
  }

  // Look for any text that might be a question (very broad search)
  const allText = document.body.innerText;
  console.log('Page text length:', allText.length);

  // Common quiz patterns to look for (includes Canvas, Blackboard, Moodle, etc.)
  const questionSelectors = [
    // Canvas New Quizzes (Learnosity) - HARDCODED FROM DEV INSPECTOR
    '.user_content > p', // Direct p tag inside user_content - the actual question text
    '.user_content.enhanced', // The actual question content in Learnosity
    '[data-automation="sdk-take-item-question"] .user_content',
    '.lrn_stimulus .user_content', // Question text wrapper
    // Canvas New Quizzes (Learnosity) - Broader selectors
    '[data-automation="sdk-take-item-question"]',
    '.lrn-assess-item__content',
    '.lrn_stimulus',
    '.lrn_question',
    '[class*="lrn_question"]',
    '[class*="lrn-question"]',
    '[class*="lrn_stimulus"]',
    '.learnosity-question',
    '[data-lrn-question-reference]',
    '.lrn_widget',
    // Canvas Classic LMS
    '.question_text',
    '.quiz_question',
    '[class*="question_text"]',
    // Blackboard
    '.questionText',
    '.vtbegenerated',
    // Moodle
    '.qtext',
    '.formulation',
    // Colibri Real Estate (uses HubSpot forms + iframes)
    '.quiz__question',
    '.question__text',
    '.assessment-question',
    '[data-question-text]',
    '.hs-form-field label',
    '.form-wrap label',
    '[class*="quiz"]',
    '[class*="assessment"]',
    '[class*="hs-form"]',
    // Generic
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    '[class*="question"]',
    '[id*="question"]',
    '[role="heading"]',
    'p strong',
    'p b',
    'div strong',
    'div b',
    '.quiz-question',
    '.question-text',
    'label',
    'p',
    'div'
  ];

  // Find the question - be very lenient
  for (const selector of questionSelectors) {
    const elements = document.querySelectorAll(selector);
    console.log(`Checking selector "${selector}": found ${elements.length} elements`);

    // DEBUG: If this is our hardcoded selector, log each element's text
    if (selector === '.user_content > p' && elements.length > 0) {
      console.log('🔍 DEBUG: .user_content > p elements:');
      elements.forEach((el, idx) => {
        console.log(`  [${idx}] Text preview: "${el.textContent.trim().substring(0, 100)}"`);
      });
    }

    for (const el of elements) {
      // For Learnosity .user_content, get ONLY the direct text, not nested answer text
      let text;
      if (el.classList.contains('user_content') || el.classList.contains('lrn_stimulus')) {
        // Clone the element to manipulate it
        const clone = el.cloneNode(true);

        // Remove any child elements that might contain answers
        const answersToRemove = clone.querySelectorAll('.lrn-mcqgroup, .lrn_mcqgroup, [class*="answer"], [class*="option"], [class*="choice"]');
        answersToRemove.forEach(child => child.remove());

        text = clone.textContent.trim();
      } else if (selector === '.user_content > p') {
        // For hardcoded .user_content > p selector, get ONLY the p tag's direct text
        // This is the cleanest question text without any navigation or metadata
        text = el.textContent.trim();
      } else {
        text = el.textContent.trim();
      }

      // Skip navigation/metadata text (Learnosity pagination)
      const isNavigationText = /question\s+at\s+position|click\s+to\s+pin|navigation\s+pane|quiz\s+navigation|multiple\s+choice\s*\d+\s+point/i.test(text);
      if (isNavigationText) {
        console.log(`Skipping navigation text: ${text.substring(0, 50)}`);
        continue;
      }

      // Skip if it looks like a page title (contains "Practice Test", "Certification", etc.)
      const isPageTitle = /practice\s+test|certification|exam\s+title|test\s+name/i.test(text);
      if (isPageTitle) {
        console.log(`Skipping page title: ${text.substring(0, 50)}`);
        continue;
      }

      // Very lenient - any text with a question mark or with question keywords
      const hasQuestionMark = text.includes('?');
      const hasKeywords = /\b(which|what|who|when|where|why|how|select|choose|give|explain|describe|discuss|analyze|compare|contrast|define|identify|list|provide|write|state|assess|evaluate|assessment|monitoring|noted|nurse|patient|client|infant|newborn|should|would|could|teaching|reason|cause|effect)\b/i.test(text);

      // For hardcoded Learnosity selectors (.user_content > p), accept ANY text length if it has keywords
      // This allows short questions like "What is 2+2"
      const isHardcodedSelector = selector === '.user_content > p' || selector === '.css-1nuqag6-formFieldLayout__label';
      const meetsLengthRequirement = isHardcodedSelector ? (text.length > 5) : (text.length > 30 && text.length < 2000);

      if ((hasQuestionMark || (hasKeywords && meetsLengthRequirement)) && text.length > 5) {
        quizData.question = text;
        quizData.found = true;
        quizData.debug.push(`Found question via selector: ${selector}`);
        console.log('✅ Found question:', text.substring(0, 100));
        break;
      }
    }
    if (quizData.found) break;
  }

  // If still not found, look for ANY paragraph with substantial text
  if (!quizData.found) {
    console.log('Trying fallback: looking for any long paragraph...');
    const allParagraphs = document.querySelectorAll('p, div');
    for (const el of allParagraphs) {
      const text = el.textContent.trim();
      // More strict fallback - must have question characteristics
      const looksLikeQuestion = text.includes('?') || /\b(which|what|select|choose|give|explain|describe|discuss|analyze|reason|cause)\b/i.test(text);
      if (text.length > 50 && text.length < 2000 && !text.includes('cookie') && !text.includes('privacy') && !text.includes('Dashboard') && looksLikeQuestion) {
        quizData.question = text;
        quizData.found = true;
        quizData.debug.push('Found question via fallback (long paragraph)');
        console.log('✅ Found question (fallback):', text.substring(0, 100));
        break;
      }
    }
  }

  // Use detected question type to optimize detection
  // Skip essay/fill-in-blank detection if we know it's multiple choice
  if (detectedQuestionType && detectedQuestionType.toLowerCase().includes('multiple choice')) {
    console.log('⚡ Skipping essay/fill-in detection - question type is Multiple Choice');
    // Jump directly to multiple choice answer detection below
  } else {
    // Check for essay/fill-in-the-blank question (textarea, text input, or contenteditable)
    const essayFields = document.querySelectorAll('textarea, input[type="text"], input:not([type="radio"]):not([type="checkbox"]):not([type="button"]):not([type="submit"]), div[contenteditable="true"]');

    // LEARNOSITY: Also check for TinyMCE rich text editor iframes
    const rceIframes = document.querySelectorAll('iframe.tox-edit-area-iframe, iframe[id*="rceTextArea"]');

    // If question type is "Essay", prioritize rich text editor
    if ((detectedQuestionType && detectedQuestionType.toLowerCase().includes('essay')) || (rceIframes.length > 0 && quizData.found)) {
      if (rceIframes.length > 0) {
        console.log(`Found ${rceIframes.length} Rich Text Editor iframe(s) (Learnosity essay question)`);

        // Use the first RCE iframe as the essay field
        const iframe = rceIframes[0];
        const iframeId = iframe.id || `studyflow-rce-${Date.now()}`;

        if (!iframe.id) {
          iframe.setAttribute('id', iframeId);
        }

        quizData.isEssay = true;
        quizData.essayFieldId = iframeId;
        quizData.isRichTextEditor = true; // Flag to indicate this is an RCE in iframe

        console.log('✅ Detected as ESSAY question (Rich Text Editor)');
        quizData.debug.push('Detected essay question with Rich Text Editor (TinyMCE iframe)');
        return quizData; // Return early, no need to look for multiple choice
      }
    }

    // LEARNOSITY: Check specifically for fill-in-the-blank inputs
    // Prioritize if question type is "Fill in the Blank"
    const learnosityFitb = document.querySelectorAll('input[data-automation="sdk-fitb-taking-answer"]');
    console.log(`🔍 Checking for Learnosity fill-in-blank: found ${learnosityFitb.length} fields`);

    if (learnosityFitb.length > 0 && (detectedQuestionType && detectedQuestionType.toLowerCase().includes('fill in the blank') || learnosityFitb.length > 0)) {
      console.log(`Found ${learnosityFitb.length} Learnosity fill-in-the-blank field(s)`);

      // If we haven't found a question yet, try to find it near the fill-in field
      if (!quizData.found) {
        console.log('⚠️ No question found yet, searching near fill-in field...');
        const field = learnosityFitb[0];

        // Try to find question in parent elements
        let parent = field.parentElement;
        let attempts = 0;
        while (parent && attempts < 10) {
          const text = parent.textContent.trim();
          // Look for substantial text that might be a question
          if (text.length > 30 && text.length < 3000) {
            quizData.question = text;
            quizData.found = true;
            quizData.debug.push('Found question near fill-in-blank field');
            console.log('✅ Found question near fill-in field:', text.substring(0, 100));
            break;
          }
          parent = parent.parentElement;
          attempts++;
        }
      }

      // If we still haven't found a question, use a generic placeholder
      if (!quizData.found) {
        console.log('⚠️ Using placeholder question text for fill-in-blank');
        quizData.question = 'Fill in the blank question (question text not detected)';
        quizData.found = true;
        quizData.debug.push('Using placeholder question for fill-in-blank');
      }

      const field = learnosityFitb[0];

      // Mark the field with a unique identifier
      const fieldId = `studyflow-field-${Date.now()}`;
      field.setAttribute('data-studyflow-field-id', fieldId);

      quizData.isEssay = true;
      quizData.essayFieldId = fieldId;

      console.log('✅ Detected as FILL-IN-THE-BLANK question (Learnosity)');
      quizData.debug.push('Detected fill-in-the-blank question (Learnosity sdk-fitb)');
      return quizData; // Return early, no need to look for multiple choice
    }

    if (essayFields.length > 0 && quizData.found) {
      console.log(`Found ${essayFields.length} text input fields`);
      // Check if the text field is visible and not a search/filter field
      for (const field of essayFields) {
        // Only consider visible fields
        if (field.offsetParent !== null) {
          // LEARNOSITY: Don't skip small fields if they have quiz-related data attributes
          const isLearnosityInput = field.hasAttribute('data-automation') && field.getAttribute('data-automation').includes('taking-answer');

          // Skip tiny fields (likely search boxes, filters, etc.) UNLESS it's a Learnosity input
          if (!isLearnosityInput && field.offsetWidth < 100 && field.tagName !== 'TEXTAREA') continue;

          // Skip fields that look like search/navigation
          const fieldText = (field.placeholder || field.name || field.id || '').toLowerCase();
          if (fieldText.includes('search') || fieldText.includes('filter') || fieldText.includes('find')) continue;

          // Mark the field with a unique identifier
          const fieldId = `studyflow-field-${Date.now()}`;
          field.setAttribute('data-studyflow-field-id', fieldId);

          quizData.isEssay = true;
          quizData.essayFieldId = fieldId;

          // Determine if it's fill-in-the-blank (short) or essay (long)
          const isFillInBlank = field.tagName === 'INPUT' && field.offsetHeight < 100;
          console.log(isFillInBlank ? '✅ Detected as FILL-IN-THE-BLANK question' : '✅ Detected as ESSAY question');
          quizData.debug.push(isFillInBlank ? 'Detected fill-in-the-blank question' : 'Detected essay question with text input field');
          return quizData; // Return early, no need to look for multiple choice
        }
      }
    }
  } // End of if-else block for question type detection

  // Find answer options (radio buttons, checkboxes, or text options)
  // Only proceed if question type is Multiple Choice or True/False (or not detected)
  if (detectedQuestionType) {
    console.log(`📋 Processing "${detectedQuestionType}" question - looking for answer options`);
  }

  // LEARNOSITY: First try hardcoded answer container selector from dev inspector
  let answerInputs = [];
  const learnosityAnswerContainer = document.querySelector('.css-d89gko-grid');

  if (learnosityAnswerContainer) {
    console.log('🎓 Found Learnosity answer container (.css-d89gko-grid), searching for inputs inside...');
    answerInputs = learnosityAnswerContainer.querySelectorAll('input[type="radio"], input[type="checkbox"]');
    console.log(`Found ${answerInputs.length} radio/checkbox inputs in Learnosity container`);
  }

  // If no Learnosity container or no inputs found, fall back to generic search
  if (answerInputs.length === 0) {
    console.log('No Learnosity container found, using generic answer detection...');
    // Also check for Learnosity (Canvas New Quizzes) and HubSpot form checkboxes
    answerInputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"], fieldset[role="radiogroup"] input[type="radio"], .fs-mask input[type="radio"], .lrn_mcqgroup input, .lrn-mcq-option input, .hs-form-checkbox input, .custom-control-input');
    console.log(`Found ${answerInputs.length} radio/checkbox inputs`);
  }

  // If no inputs found, the quiz might use clickable divs instead
  if (answerInputs.length === 0) {
    console.log('No radio buttons found, looking for clickable answer divs...');
    // We'll still return found=false if we can't find clickable answers
    // But at least we tried
  }

  answerInputs.forEach((input, index) => {
    // Find associated label or nearby text
    let answerText = '';

    // Try to find label by 'for' attribute
    if (input.id) {
      const label = document.querySelector(`label[for="${input.id}"]`);
      if (label) {
        answerText = label.textContent.trim();
      }
    }

    // Try parent label
    if (!answerText) {
      const parentLabel = input.closest('label');
      if (parentLabel) {
        answerText = parentLabel.textContent.trim();
      }
    }

    // LEARNOSITY: Try to find .user_content in parent structure
    if (!answerText) {
      const parentGridCol = input.closest('[class*="gridCol"]');
      if (parentGridCol) {
        const userContent = parentGridCol.querySelector('.user_content');
        if (userContent) {
          answerText = userContent.textContent.trim();
        }
      }
    }

    // LEARNOSITY: Try to find answer label in sibling span
    if (!answerText) {
      const labelSpan = input.closest('[class*="radioInput"]')?.querySelector('[class*="radioInput__label"]');
      if (labelSpan) {
        answerText = labelSpan.textContent.trim();
      }
    }

    // Try next sibling
    if (!answerText && input.nextSibling) {
      answerText = input.nextSibling.textContent?.trim() || '';
    }

    // Try parent div text
    if (!answerText) {
      const parent = input.parentElement;
      if (parent) {
        answerText = parent.textContent.trim();
      }
    }

    // Clean up answer text (remove extra whitespace)
    answerText = answerText.replace(/\s+/g, ' ').trim();

    if (answerText && answerText.length > 0 && answerText.length < 500) {
      quizData.answers.push({
        index: index + 1,
        text: answerText,
        element: input,
        type: input.type
      });
      console.log(`✅ Answer ${index + 1}:`, answerText.substring(0, 50));
      quizData.debug.push(`Found answer ${index + 1}: ${answerText.substring(0, 30)}...`);
    }
  });

  console.log(`Total answers found: ${quizData.answers.length}`);

  // Determine if this is a multiple-answer question (checkboxes)
  if (quizData.answers.length > 0) {
    const isMultipleAnswer = quizData.answers[0].type === 'checkbox';
    quizData.isMultipleAnswer = isMultipleAnswer;
    console.log(`Question type: ${isMultipleAnswer ? 'MULTIPLE-ANSWER (checkboxes)' : 'single-answer (radio)'}`);
  }

  // CRITICAL VALIDATION: Don't return quiz data if we have a question but NO answers
  // This prevents false positives like detecting "Dashboard" as a question
  if (quizData.found && quizData.answers.length === 0 && !quizData.isEssay) {
    console.log('⚠️ Found question but no answers - likely not a real quiz question, ignoring');
    return {
      question: '',
      answers: [],
      found: false,
      debug: ['Rejected: Question found but no answers detected']
    };
  }

  return quizData;
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'detectQuiz') {
    // Check if one-page mode is enabled
    const onePageMode = request.onePageMode || false;

    if (onePageMode) {
      console.log('📄 ONE-PAGE MODE enabled');
      const quizData = detectOnePageQuiz();
      sendResponse(quizData);
    } else {
      console.log('📄 SEQUENTIAL MODE (default)');
      const quizData = detectQuiz();
      sendResponse(quizData);
    }
  } else if (request.action === 'resetAnsweredQuestions') {
    // Reset tracking when quiz starts
    answeredQuestions.clear();
    answeredLearnosityQuestions.clear();
    console.log('🔄 Reset answered questions tracker (generic + Learnosity)');
    sendResponse({ success: true });
  } else if (request.action === 'markQuestionAnswered') {
    // Mark a question as answered after it's been successfully processed
    const questionHash = request.questionHash;
    if (questionHash) {
      answeredLearnosityQuestions.add(questionHash);
      console.log(`✅ Marked question as answered: ${questionHash.substring(0, 20)}...`);
    }
    sendResponse({ success: true });
  } else if (request.action === 'clickAnswer') {
    const answerIndex = request.answerIndex;
    const radioGroupId = request.radioGroupId;

    let input;
    if (radioGroupId) {
      // One-page mode: find the specific radio button by group ID and index
      input = document.querySelector(`[data-studyflow-radio-group="${radioGroupId}"][data-studyflow-radio-index="${answerIndex - 1}"]`);
    } else {
      // Sequential mode: use all radio buttons on page
      const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
      input = inputs[answerIndex - 1];
    }

    if (input) {
      // Scroll into view
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // HUMAN-LIKE DELAY: Random delay between 1-2.5 seconds
      const humanDelay = 1000 + Math.random() * 1500;

      setTimeout(() => {
        // Check if this is a Learnosity quiz
        const isLearnosity = window.location.hostname.includes('learnosity.com') ||
                           document.querySelector('[data-automation]') !== null;

        if (isLearnosity) {
          console.log('🎓 Learnosity detected, using human-like click sequence...');

          // Simulate mouse movement and hover before click
          input.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
          input.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

          setTimeout(() => {
            // Focus before clicking (human behavior)
            input.focus();

            setTimeout(() => {
              // Click with proper mouse events
              input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
              input.click();
              input.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));

              // Brief highlight to confirm click
              const parent = input.closest('label') || input.parentElement;
              if (parent) {
                const originalBg = parent.style.backgroundColor;
                parent.style.backgroundColor = '#90EE90';
                parent.style.transition = 'background-color 0.3s';
                setTimeout(() => {
                  parent.style.backgroundColor = originalBg;
                }, 800); // Shorter duration - just a quick flash
              }

              console.log('✅ Clicked answer with human-like interaction');
              sendResponse({ success: true });
            }, 150); // Small delay between focus and click
          }, 200); // Small delay between hover and focus
        } else {
          // Non-Learnosity - use faster method
          input.click();

          // Brief highlight to confirm click
          const parent = input.closest('label') || input.parentElement;
          if (parent) {
            const originalBg = parent.style.backgroundColor;
            parent.style.backgroundColor = '#90EE90';
            parent.style.transition = 'background-color 0.3s';
            setTimeout(() => {
              parent.style.backgroundColor = originalBg;
            }, 800); // Shorter duration - just a quick flash
          }

          sendResponse({ success: true });
        }
      }, humanDelay);
    } else {
      console.error('Radio button not found. answerIndex:', answerIndex, 'radioGroupId:', radioGroupId);
      sendResponse({ success: false, error: 'Answer not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'fillEssay') {
    // Fill in essay answer
    const essayAnswer = request.essayAnswer;
    const essayFieldId = request.essayFieldId;
    const isRichTextEditor = request.isRichTextEditor;

    // LEARNOSITY: Check if this is a Rich Text Editor iframe
    if (isRichTextEditor) {
      const iframe = document.querySelector(`[data-studyflow-field-id="${essayFieldId}"]`);

      if (iframe && iframe.tagName === 'IFRAME') {
        iframe.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
          try {
            // Access the iframe's content
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            const body = iframeDoc.body;

            if (body && body.contentEditable === 'true') {
              // Set the content in the TinyMCE editor
              body.innerHTML = essayAnswer;

              // Trigger events
              body.dispatchEvent(new Event('input', { bubbles: true }));
              body.dispatchEvent(new Event('change', { bubbles: true }));

              // Highlight briefly
              body.style.backgroundColor = '#90EE90';
              body.style.transition = 'background-color 0.3s';
              setTimeout(() => {
                body.style.backgroundColor = '';
              }, 2000);

              console.log('✅ Filled Rich Text Editor with essay answer');
              sendResponse({ success: true });
            } else {
              console.error('RCE body not found or not editable');
              sendResponse({ success: false, error: 'RCE body not editable' });
            }
          } catch (err) {
            console.error('Error accessing iframe content:', err);
            sendResponse({ success: false, error: 'Cannot access iframe: ' + err.message });
          }
        }, 500);

        return true; // Keep channel open for async response
      } else {
        console.error('Rich Text Editor iframe not found with ID:', essayFieldId);
        sendResponse({ success: false, error: 'RCE iframe not found' });
        return true;
      }
    }

    // Standard essay field (not RCE)
    const field = document.querySelector(`[data-studyflow-field-id="${essayFieldId}"]`);

    if (field) {
      field.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // HUMAN-LIKE DELAY: Wait 1-2 seconds before starting to type
      const initialDelay = 1000 + Math.random() * 1000;

      setTimeout(() => {
        // Set the value
        if (field.tagName === 'TEXTAREA' || field.tagName === 'INPUT') {
          // Focus the field first (human-like)
          field.focus();

          // Check if this is a Learnosity field (needs special handling)
          const isLearnosityField = field.hasAttribute('data-automation');

          if (isLearnosityField) {
            console.log('🎓 Detected Learnosity field, using human-like typing...');

            // SIMULATE HUMAN TYPING character by character
            let currentText = '';
            let charIndex = 0;

            const typeNextChar = () => {
              if (charIndex < essayAnswer.length) {
                currentText += essayAnswer[charIndex];

                // Use native setter to bypass React
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                  window.HTMLInputElement.prototype,
                  'value'
                ).set;
                nativeInputValueSetter.call(field, currentText);

                // Trigger events after each character
                field.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, data: essayAnswer[charIndex] }));

                charIndex++;

                // Random delay between 50-150ms per character (human-like typing speed)
                const charDelay = 50 + Math.random() * 100;
                setTimeout(typeNextChar, charDelay);
              } else {
                // Done typing - trigger final events
                field.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));

                // Blur after a short delay (human-like)
                setTimeout(() => {
                  field.blur();

                  // Highlight the field briefly
                  field.style.backgroundColor = '#90EE90';
                  field.style.transition = 'background-color 0.3s';
                  setTimeout(() => {
                    field.style.backgroundColor = '';
                  }, 2000);

                  console.log('✅ Filled Learnosity field with human-like typing');
                  sendResponse({ success: true });
                }, 300);
              }
            };

            // Start typing
            typeNextChar();
          } else {
            // Non-Learnosity field - use faster method
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype,
              'value'
            ).set;
            const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(
              window.HTMLTextAreaElement.prototype,
              'value'
            ).set;

            if (field.tagName === 'INPUT') {
              nativeInputValueSetter.call(field, essayAnswer);
            } else {
              nativeTextAreaValueSetter.call(field, essayAnswer);
            }

            // Trigger React events
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            field.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));

            // Blur to ensure React updates
            setTimeout(() => {
              field.blur();

              // Highlight the field briefly
              field.style.backgroundColor = '#90EE90';
              field.style.transition = 'background-color 0.3s';
              setTimeout(() => {
                field.style.backgroundColor = '';
              }, 2000);

              console.log('✅ Filled text field with answer');
              sendResponse({ success: true });
            }, 300);
          }
        } else if (field.contentEditable === 'true') {
          field.textContent = essayAnswer;
          field.dispatchEvent(new Event('input', { bubbles: true }));

          setTimeout(() => {
            sendResponse({ success: true });
          }, 300);
        }
      }, initialDelay);
    } else {
      console.error('Essay field not found with ID:', essayFieldId);
      sendResponse({ success: false, error: 'Essay field not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'clickSubmit') {
    // Find and click the submit button
    console.log('Looking for submit button...');

    // Check if we're on Learnosity/Canvas LTI (don't auto-click to avoid 403)
    const isLearnosity = window.location.hostname.includes('learnosity.com');
    const isCanvasLTI = window.location.hostname.includes('quiz-lti') || window.location.hostname.includes('canvas');

    let submitButton = null;

    // First try: button[type="submit"] or input[type="submit"]
    const typeSubmitButtons = document.querySelectorAll('button[type="submit"], input[type="submit"]');
    if (typeSubmitButtons.length > 0) {
      submitButton = typeSubmitButtons[0];
      console.log('Found submit button by type="submit"');
    }

    // Second try: all buttons, search by text
    if (!submitButton) {
      const allButtons = document.querySelectorAll('button, input[type="button"], a.button, a.btn');
      for (const btn of allButtons) {
        const text = (btn.textContent || btn.value || '').toLowerCase().trim();
        console.log(`Checking button text: "${text}"`);

        if (text === 'submit' ||
            text === 'next' ||
            text === 'continue' ||
            text === 'check' ||
            text.includes('submit') ||
            text.includes('next')) {
          submitButton = btn;
          console.log(`✅ Found button by text: "${text}"`);
          break;
        }
      }
    }

    // Third try: any button on the page (last resort)
    if (!submitButton) {
      const anyButtons = document.querySelectorAll('button');
      console.log(`Found ${anyButtons.length} total buttons on page`);

      // Log all button texts for debugging
      anyButtons.forEach((btn, i) => {
        console.log(`Button ${i}: "${btn.textContent.trim()}"`);
      });

      if (anyButtons.length > 0) {
        // Use the first visible button as last resort
        for (const btn of anyButtons) {
          if (btn.offsetParent !== null) { // Check if visible
            submitButton = btn;
            console.log(`Using first visible button: "${btn.textContent.trim()}"`);
            break;
          }
        }
      }
    }

    if (submitButton) {
      submitButton.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // Use human-like click for Learnosity/Canvas to avoid 403 errors
      if (isLearnosity || isCanvasLTI) {
        console.log('🎓 Learnosity detected, using human-like click sequence...');

        // Brief highlight to show button was found
        submitButton.style.boxShadow = '0 0 20px 5px #4CAF50';
        submitButton.style.border = '2px solid #4CAF50';

        setTimeout(() => {
          // Remove highlight
          submitButton.style.boxShadow = '';
          submitButton.style.border = '';

          // HUMAN-LIKE CLICK SEQUENCE (same as answer clicking)
          const rect = submitButton.getBoundingClientRect();
          const x = rect.left + rect.width / 2;
          const y = rect.top + rect.height / 2;

          // 1. Dispatch mouseover
          submitButton.dispatchEvent(new MouseEvent('mouseover', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: x,
            clientY: y
          }));

          setTimeout(() => {
            // 2. Dispatch mousedown
            submitButton.dispatchEvent(new MouseEvent('mousedown', {
              bubbles: true,
              cancelable: true,
              view: window,
              clientX: x,
              clientY: y,
              button: 0
            }));

            setTimeout(() => {
              // 3. Focus the element
              if (submitButton.focus) {
                submitButton.focus();
              }

              setTimeout(() => {
                // 4. Dispatch mouseup
                submitButton.dispatchEvent(new MouseEvent('mouseup', {
                  bubbles: true,
                  cancelable: true,
                  view: window,
                  clientX: x,
                  clientY: y,
                  button: 0
                }));

                setTimeout(() => {
                  // 5. Direct click (most reliable method)
                  submitButton.click();

                  console.log('✅ Clicked submit button with human-like interaction');
                  sendResponse({ success: true });
                }, 50 + Math.random() * 50);
              }, 50 + Math.random() * 50);
            }, 50 + Math.random() * 50);
          }, 50 + Math.random() * 50);
        }, 800); // Wait 800ms after highlight
      } else {
        // Not Learnosity - safe to auto-click
        setTimeout(() => {
          console.log('Clicking submit button (non-Learnosity site)');
          submitButton.click();
          sendResponse({ success: true });
        }, 500);
      }
    } else {
      console.log('❌ No submit button found');
      sendResponse({ success: false, error: 'Submit button not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'showAlert') {
    // Show alert message to user
    alert(request.message);
    sendResponse({ success: true });
  } else if (request.action === 'clearHighlight') {
    // Remove the tooltip and button highlight
    const tooltip = document.getElementById('studyflow-submit-tooltip');
    if (tooltip) {
      tooltip.remove();
    }
    sendResponse({ success: true });
  }
});

// Listen for page unload (navigation) to clean up UI
window.addEventListener('beforeunload', () => {
  // Remove tooltip if it exists
  const tooltip = document.getElementById('studyflow-submit-tooltip');
  if (tooltip) {
    tooltip.remove();
  }
});

// Also clean up when page becomes hidden (tab switch or navigation)
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    const tooltip = document.getElementById('studyflow-submit-tooltip');
    if (tooltip) {
      tooltip.remove();
    }
  }
});

// Notify that script is ready
console.log('StudyFlowSuite ready to detect quizzes');

} // End of initializeExtension()
