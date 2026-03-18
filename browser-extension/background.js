// Background service worker - runs the quiz loop independently
const BACKEND_URL = 'https://studyflowsuite.onrender.com';

let isRunning = false;
let questionCount = 0;
let errorCount = 0;
let lastQuestionText = null;
let sameQuestionCount = 0;
let currentTabId = null;
let latestAnswer = null;

// Quiz settings
let quizSettings = {
  totalQuestions: null,
  targetTime: null, // in minutes
  skipEssays: false,
  onePageMode: false
};
let quizStartTime = null;

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'start') {
    startQuizMode(request.tabId, request.settings);
    sendResponse({ success: true });
  } else if (request.action === 'stop') {
    stopQuizMode();
    sendResponse({ success: true });
  } else if (request.action === 'getStatus') {
    sendResponse({
      isRunning,
      questionCount,
      errorCount,
      currentQuestion: lastQuestionText?.substring(0, 100),
      latestAnswer
    });
  }
  return true;
});

function startQuizMode(tabId, settings = {}) {
  if (isRunning) return;

  isRunning = true;
  currentTabId = tabId;
  questionCount = 0;
  errorCount = 0;
  lastQuestionText = null;
  sameQuestionCount = 0;
  quizSettings = settings;
  quizStartTime = Date.now();

  console.log('Starting quiz mode on tab:', tabId);
  console.log('Quiz settings:', quizSettings);
  updateBadge('▶', '#00c853');

  // Reset answered questions tracker in content script
  chrome.tabs.sendMessage(tabId, { action: 'resetAnsweredQuestions' });

  runQuizLoop();
}

function stopQuizMode() {
  isRunning = false;
  currentTabId = null;
  quizSettings = { totalQuestions: null, targetTime: null, skipEssays: false, onePageMode: false };
  quizStartTime = null;
  console.log('Quiz mode stopped');
  updateBadge('', '');
}

async function runQuizLoop() {
  while (isRunning) {
    try {
      // Detect quiz on current tab
      const quiz = await new Promise((resolve) => {
        chrome.tabs.sendMessage(currentTabId, {
          action: 'detectQuiz',
          onePageMode: quizSettings.onePageMode
        }, (response) => {
          if (chrome.runtime.lastError) {
            console.error('Error:', chrome.runtime.lastError);
            resolve(null);
          } else {
            resolve(response);
          }
        });
      });

      if (!quiz || !quiz.found) {
        // Check if this is the end of a one-page quiz
        if (quiz && quiz.debug && quiz.debug.includes('One-page quiz: all questions completed')) {
          console.log('✅ One-page quiz completed! All questions answered.');
          console.log('Clicking submit button...');

          // Click submit for the whole quiz
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
          });

          await sleep(2000);
          stopQuizMode();
          break;
        }

        console.log('No quiz found, waiting...');
        await sleep(2000);
        continue;
      }

      // Check if one-page mode is enabled
      const isOnePageQuiz = quizSettings.onePageMode;

      // Check if it's an essay question
      if (quiz.isEssay) {
        console.log('📝 Essay question detected');

        if (quizSettings.skipEssays) {
          console.log('⏭️ Skipping essay question (skip essays enabled)');
          await sleep(2000);
          continue; // Skip this question
        }

        console.log('Writing AI essay answer...');

        // Get essay answer from AI
        const essayAnswer = await getEssayAnswer(quiz.question);
        console.log('AI Essay Answer:', essayAnswer.substring(0, 100));

        // Fill in the essay field
        await new Promise((resolve) => {
          chrome.tabs.sendMessage(currentTabId, {
            action: 'fillEssay',
            essayAnswer: essayAnswer
          }, resolve);
        });

        await sleep(1500);

        // Only click submit if NOT a one-page quiz
        if (!isOnePageQuiz) {
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
          });
        }

        questionCount++;
        console.log(`✅ Essay question ${questionCount} completed`);
        updateBadge(questionCount.toString(), '#00c853');

        // Check if we've hit the total questions limit
        if (quizSettings.totalQuestions && questionCount >= quizSettings.totalQuestions) {
          console.log('🎉 Reached total questions limit. Stopping quiz.');

          // If one-page quiz, click submit now
          if (isOnePageQuiz) {
            await new Promise((resolve) => {
              chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
            });
          }

          stopQuizMode();
          break;
        }

        // Use smart delay
        const delay = calculateSmartDelay();
        await sleep(delay);
        continue; // Skip the multiple choice logic below
      }

      // Check if same question
      const currentQuestionText = quiz.question.substring(0, 200);
      if (currentQuestionText === lastQuestionText) {
        sameQuestionCount++;
        console.log(`Same question (count: ${sameQuestionCount})`);

        if (sameQuestionCount > 10) {
          console.log('⚠️ Stuck, resetting...');
          lastQuestionText = null;
          sameQuestionCount = 0;
          errorCount++;
          updateBadge('⚠️', '#f44336');
          await sleep(5000);
          continue;
        }

        await sleep(2000);
        continue;
      }

      // New question!
      sameQuestionCount = 0;
      lastQuestionText = currentQuestionText;
      console.log('New question detected:', currentQuestionText.substring(0, 50));

      // Get AI answer
      const answer = await getAIAnswer(quiz);
      console.log('AI Answer:', answer.correct_index);

      // Clean the question text (remove common headers)
      let cleanQuestion = quiz.question;
      const headerPatterns = [
        /^.*?Practice Test\s*/i,
        /^.*?Certification\s*/i,
        /^.*?Exam\s*/i,
        /^Question\s+\d+\s*/i,
        /^\d+\.\s*/,
        /^Q\d+[\s:]+/i
      ];

      for (const pattern of headerPatterns) {
        cleanQuestion = cleanQuestion.replace(pattern, '');
      }
      cleanQuestion = cleanQuestion.trim();

      // Store latest answer for history (with unique ID to prevent duplicates)
      const answerText = quiz.answers[answer.correct_index - 1]?.text || `Answer #${answer.correct_index}`;
      latestAnswer = {
        id: `${Date.now()}-${currentQuestionText.substring(0, 50)}`, // Unique ID
        question: cleanQuestion,
        answer: answerText,
        reasoning: answer.reasoning,
        timestamp: Date.now()
      };

      // Click answer
      await new Promise((resolve) => {
        chrome.tabs.sendMessage(currentTabId, {
          action: 'clickAnswer',
          answerIndex: answer.correct_index
        }, resolve);
      });

      await sleep(1500);

      // Only click submit if NOT a one-page quiz
      if (!isOnePageQuiz) {
        await new Promise((resolve) => {
          chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
        });
      }

      questionCount++;
      console.log(`✅ Question ${questionCount} completed`);
      updateBadge(questionCount.toString(), '#00c853');

      // Check if we've hit the total questions limit
      if (quizSettings.totalQuestions && questionCount >= quizSettings.totalQuestions) {
        console.log('🎉 Reached total questions limit. Stopping quiz.');

        // If one-page quiz, click submit now
        if (isOnePageQuiz) {
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
          });
        }

        stopQuizMode();
        break;
      }

      // Use smart delay based on target time
      const delay = calculateSmartDelay();
      await sleep(delay);

    } catch (error) {
      console.error('❌ Error in quiz loop:', error);
      console.error('Error details:', error.message);
      console.error('Stack trace:', error.stack);
      errorCount++;
      updateBadge('❌', '#f44336');
      await sleep(3000);
    }
  }

  updateBadge('', '');
}

async function getAIAnswer(quiz) {
  const response = await fetch(`${BACKEND_URL}/api/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: quiz.question,
      answers: quiz.answers.map(a => a.text)
    })
  });

  if (!response.ok) {
    throw new Error('Failed to get AI answer');
  }

  const data = await response.json();
  return {
    correct_index: data.correct_answer_index,
    reasoning: data.reasoning || 'No explanation provided'
  };
}

async function getEssayAnswer(question) {
  const response = await fetch(`${BACKEND_URL}/api/essay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: question
    })
  });

  if (!response.ok) {
    throw new Error('Failed to get AI essay answer');
  }

  const data = await response.json();
  return data.essay_answer || 'No answer generated';
}

function updateBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Calculate smart delay for next question based on target time
function calculateSmartDelay() {
  // If no target time set, return no delay (0 seconds)
  if (!quizSettings.targetTime || !quizSettings.totalQuestions) {
    return 0;
  }

  const elapsedMinutes = (Date.now() - quizStartTime) / 1000 / 60;
  const remainingMinutes = quizSettings.targetTime - elapsedMinutes;
  const questionsLeft = quizSettings.totalQuestions - questionCount;

  // If we're out of time or done, use minimal delay
  if (remainingMinutes <= 0 || questionsLeft <= 0) {
    return 2000;
  }

  // Calculate average time per question remaining (in milliseconds)
  const avgTimePerQuestion = (remainingMinutes / questionsLeft) * 60 * 1000;

  // Add randomization (±30%) to make it feel more human
  const variation = avgTimePerQuestion * 0.3;
  const randomDelay = avgTimePerQuestion + (Math.random() * variation * 2 - variation);

  // Ensure delay is between 2-30 seconds for realism
  const clampedDelay = Math.max(2000, Math.min(30000, randomDelay));

  console.log(`Smart delay: ${Math.round(clampedDelay / 1000)}s (${questionsLeft} questions left, ${remainingMinutes.toFixed(1)}min remaining)`);

  return clampedDelay;
}

console.log('StudyFlowSuite background worker loaded');
