'use strict';

/* ------------------------------------------------------------------ */
/* API 클라이언트 — 모든 fetch 호출은 이 객체를 통해서만 이루어진다.    */
/* ------------------------------------------------------------------ */

const API_BASE = '/api';

// 일반 조회 API 타임아웃. 정보나루는 백엔드에서 8초 단일 시도(재시도 0, ADR-0004)라
// 10초면 충분하다.
const API_TIMEOUT_MS = 10000;

// generate 전용 타임아웃. 백엔드 LLM 호출은 15초 × 최대 2회(1차 + 재시도 1회) =
// 최대 30초까지 걸릴 수 있다(llm.py LLM_TIMEOUT/LLM_MAX_ATTEMPTS, ADR-0004).
// 이 값이 30초보다 짧으면 1차 호출이 느릴 때 프론트가 먼저 abort 해서, 재시도가
// 성공해도 사용자는 항상 에러 화면을 보게 된다 — 1계층 폴백이 무력화된다.
// 30초 + 네트워크·렌더 여유 5초 = 35초.
const GENERATE_TIMEOUT_MS = 35000;

// PDF 렌더는 Chromium 기동 포함이라 별도 여유값.
const PDF_TIMEOUT_MS = 30000;

function fetchJson(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const opts = Object.assign({}, options, { signal: controller.signal });

    return fetch(url, opts)
        .then((res) => {
            if (!res.ok) {
                throw new Error('HTTP ' + res.status);
            }
            return res.json();
        })
        .finally(() => clearTimeout(timer));
}

const api = {
    getStories() {
        return fetchJson(API_BASE + '/stories', {}, API_TIMEOUT_MS);
    },
    getStory(id) {
        return fetchJson(API_BASE + '/stories/' + encodeURIComponent(id), {}, API_TIMEOUT_MS);
    },
    generateStory(id, payload) {
        return fetchJson(
            API_BASE + '/stories/' + encodeURIComponent(id) + '/generate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            },
            GENERATE_TIMEOUT_MS
        );
    },
    getRecommendations(sessionId) {
        return fetchJson(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/recommendations', {}, API_TIMEOUT_MS);
    },
    // 아이 이름은 URL(쿼리스트링)이 아니라 POST 바디로만 보낸다 — 서버 액세스 로그·
    // 브라우저 히스토리에 이름이 남지 않게 하기 위함(NFR-6 / ADR-0005).
    fetchPdfBlob(sessionId, authorName) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), PDF_TIMEOUT_MS);

        return fetch(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author_name: authorName }),
            signal: controller.signal
        })
            .then((res) => {
                if (!res.ok) {
                    throw new Error('HTTP ' + res.status);
                }
                return res.blob();
            })
            .finally(() => clearTimeout(timer));
    }
};

/* ------------------------------------------------------------------ */
/* 상태                                                                */
/* ------------------------------------------------------------------ */

const state = {
    lang: 'ko',
    stories: [],
    currentStory: null,
    sessionId: null,
    pages: [],
    keywords: [],
    recognizing: false,
    finalTranscript: ''
};

/* ------------------------------------------------------------------ */
/* DOM 캐시 (init에서 채움)                                            */
/* ------------------------------------------------------------------ */

let el = {};
let recognition = null;

/* ------------------------------------------------------------------ */
/* 화면 전환                                                           */
/* ------------------------------------------------------------------ */

function goTo(screenId) {
    document.querySelectorAll('.screen').forEach((node) => node.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}

/* ------------------------------------------------------------------ */
/* 화면 2: 서가 목록                                                    */
/* ------------------------------------------------------------------ */

function clearChildren(node) {
    while (node.firstChild) {
        node.removeChild(node.firstChild);
    }
}

function renderBookGridMessage(message) {
    clearChildren(el.bookGrid);
    const msg = document.createElement('div');
    msg.className = 'book-grid-empty';
    msg.textContent = message;
    el.bookGrid.appendChild(msg);
}

function renderBookGrid(stories) {
    clearChildren(el.bookGrid);
    if (!stories.length) {
        renderBookGridMessage('아직 등록된 이야기가 없어요.');
        return;
    }
    stories.forEach((story) => {
        const card = document.createElement('div');
        card.className = 'book-card';

        const emoji = document.createElement('div');
        emoji.className = 'book-emoji';
        emoji.textContent = story.emoji || '📖';

        // 표지 이미지가 있으면 카드 상단을 그림으로 채우고, 없거나 404 면 이모지로 폴백한다
        // (딱지본 스캔과 같은 규칙 — 빈 액자를 남기지 않는다).
        if (story.cover_image) {
            const cover = document.createElement('img');
            cover.className = 'book-cover';
            cover.alt = '';
            cover.loading = 'lazy';
            cover.onerror = () => { card.replaceChild(emoji, cover); };
            cover.src = story.cover_image;
            card.appendChild(cover);
        } else {
            card.appendChild(emoji);
        }

        const textWrap = document.createElement('div');
        textWrap.className = 'book-text-wrap';

        const keyword = document.createElement('span');
        keyword.className = 'book-keyword';
        keyword.textContent = story.keyword || '';

        const title = document.createElement('span');
        title.className = 'book-title';
        title.textContent = story.title || '';

        textWrap.appendChild(keyword);
        textWrap.appendChild(title);
        card.appendChild(textWrap);

        card.addEventListener('click', () => selectStory(story.id));
        el.bookGrid.appendChild(card);
    });
}

async function loadStories() {
    renderBookGridMessage('이야기를 불러오는 중...');
    el.storyCount.textContent = '전래동화 0 책(冊)';
    try {
        const stories = await api.getStories();
        state.stories = Array.isArray(stories) ? stories : [];
        renderBookGrid(state.stories);
        el.storyCount.textContent = '전래동화 ' + state.stories.length + ' 책(冊)';
    } catch (err) {
        console.error('failed to load stories', err);
        renderBookGridMessage('이야기를 불러오지 못했어요. 다시 시도해 주세요.');
    }
}

/* ------------------------------------------------------------------ */
/* 화면 3: 이야기 앞부분                                                */
/* ------------------------------------------------------------------ */

// 딱지본 스캔은 아직 확보되지 않은 이야기가 있다. 경로가 없거나 파일이 404 면
// 빈 액자가 남지 않도록 영역째 숨긴다(요약 텍스트만으로도 화면이 성립한다).
function showIntroImage(path) {
    if (!path) {
        el.introImageWrap.style.display = 'none';
        return;
    }
    el.introImage.onerror = () => { el.introImageWrap.style.display = 'none'; };
    el.introImage.onload = () => { el.introImageWrap.style.display = 'block'; };
    el.introImage.src = path;
}

async function selectStory(id) {
    try {
        const detail = await api.getStory(id);
        state.currentStory = detail;
        el.storyTitle.textContent = detail.title || '';
        el.introSummary.textContent = detail.intro_summary || '';
        showIntroImage(detail.intro_image);
    } catch (err) {
        console.error('failed to load story detail', err);
        state.currentStory = { id: id, title: '' };
        el.storyTitle.textContent = '-';
        el.introSummary.textContent = '이야기를 불러오지 못했어요. 다시 시도해 주세요.';
        showIntroImage(null);
    }
    goTo('screen3');
}

/* ------------------------------------------------------------------ */
/* 화면 4: 구술 입력 + Web Speech API                                  */
/* ------------------------------------------------------------------ */

function updateAiButtonState() {
    const text = el.sttBox.textContent.trim();
    el.aiBtn.disabled = text.length < 1;
}

function resetSpeechState() {
    if (recognition && state.recognizing) {
        try {
            recognition.stop();
        } catch (err) {
            /* ignore */
        }
    }
    state.finalTranscript = '';
    el.sttBox.textContent = '';
    hideGenerateError();
    updateAiButtonState();
}

function setMicIdleStyle() {
    el.micBtn.style.animation = 'pulse 2s infinite';
    el.micBtn.style.backgroundColor = 'var(--primary-celadon)';
}

function setMicActiveStyle() {
    el.micBtn.style.animation = 'pulse 1s infinite';
    el.micBtn.style.backgroundColor = 'var(--accent-red)';
}

function handleRecognitionResult(event) {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
            state.finalTranscript += transcript;
        } else {
            interim += transcript;
        }
    }
    el.sttBox.textContent = (state.finalTranscript + interim).trim();
    updateAiButtonState();
}

function handleRecognitionEnd() {
    state.recognizing = false;
    setMicIdleStyle();
}

function handleRecognitionError(event) {
    console.error('speech recognition error', event.error);
    state.recognizing = false;
    setMicIdleStyle();
}

function toggleRecord() {
    if (!recognition) {
        return;
    }
    if (!state.recognizing) {
        recognition.lang = state.lang === 'en' ? 'en-US' : 'ko-KR';
        try {
            recognition.start();
            state.recognizing = true;
            setMicActiveStyle();
        } catch (err) {
            console.error('failed to start recognition', err);
        }
    } else {
        recognition.stop();
    }
}

function initSpeechRecognition() {
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
        el.micBtn.disabled = true;
        el.micUnsupportedNote.classList.add('visible');
        return;
    }
    recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = handleRecognitionResult;
    recognition.onerror = handleRecognitionError;
    recognition.onend = handleRecognitionEnd;
}

function showGenerateError() {
    el.generateError.classList.add('visible');
}

function hideGenerateError() {
    el.generateError.classList.remove('visible');
}

/* ------------------------------------------------------------------ */
/* AI 생성                                                             */
/* ------------------------------------------------------------------ */

async function handleGenerate() {
    if (!state.currentStory || state.currentStory.id === undefined) {
        return;
    }
    const childSpeech = el.sttBox.textContent.trim();
    if (childSpeech.length < 1) {
        return;
    }
    hideGenerateError();
    goTo('loadingScreen');
    try {
        const data = await api.generateStory(state.currentStory.id, {
            lang: state.lang,
            child_speech: childSpeech
        });
        state.sessionId = data.session_id;
        state.pages = Array.isArray(data.pages) ? data.pages : [];
        state.keywords = Array.isArray(data.keywords) ? data.keywords : [];
        renderPdfPages(state.pages);
        goTo('screen5');
    } catch (err) {
        console.error('generate failed', err);
        goTo('screen4');
        showGenerateError();
    }
}

/* ------------------------------------------------------------------ */
/* 화면 5: 완성본 / PDF                                                 */
/* ------------------------------------------------------------------ */

function renderPdfPages(pages) {
    clearChildren(el.pdfScrollBox);
    pages.forEach((page) => {
        const pageEl = document.createElement('div');
        pageEl.className = 'pdf-page';

        const drawArea = document.createElement('div');
        drawArea.className = 'pdf-draw-area';
        drawArea.textContent = '그림 그리는 곳';

        const textArea = document.createElement('div');
        textArea.className = 'pdf-text-area';
        textArea.appendChild(document.createTextNode(page.ko || ''));

        const enLine = document.createElement('div');
        enLine.className = 'pdf-text-en';
        enLine.textContent = page.en || '';
        textArea.appendChild(enLine);

        pageEl.appendChild(drawArea);
        pageEl.appendChild(textArea);
        el.pdfScrollBox.appendChild(pageEl);
    });
}

function showPdfError() {
    el.pdfError.classList.add('visible');
}

function hidePdfError() {
    el.pdfError.classList.remove('visible');
}

function pdfFileName() {
    // 파일명에는 아이 이름을 넣지 않는다 — 다운로드 폴더에 이름이 남기 때문.
    const title = (state.currentStory && state.currentStory.title) || '우리동화';
    return title.replace(/[\\/:*?"<>|]/g, '') + '_동화책.pdf';
}

async function handleDownloadPdf() {
    if (!state.sessionId) {
        return;
    }
    const authorName = el.authorNameInput.value.trim();
    hidePdfError();
    el.downloadPdfBtn.disabled = true;
    try {
        const blob = await api.fetchPdfBlob(state.sessionId, authorName);
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = pdfFileName();
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(objectUrl);
    } catch (err) {
        console.error('pdf download failed', err);
        showPdfError();
    } finally {
        el.downloadPdfBtn.disabled = false;
    }
}

/* ------------------------------------------------------------------ */
/* 영수증 모달                                                          */
/* ------------------------------------------------------------------ */

function formatNow() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return y + '. ' + m + '. ' + d;
}

function renderReceiptBooks(books) {
    clearChildren(el.receiptBooks);
    if (!books || !books.length) {
        const empty = document.createElement('div');
        empty.textContent = '추천 도서가 없어요.';
        el.receiptBooks.appendChild(empty);
        return;
    }
    books.forEach((book, idx) => {
        const row = document.createElement('div');
        row.className = 'receipt-book-row';

        const name = document.createElement('span');
        name.textContent = (idx + 1) + '. ' + (book.title || '');

        const code = document.createElement('strong');
        code.className = 'receipt-book-code';
        code.textContent = book.call_number || '';

        row.appendChild(name);
        row.appendChild(code);
        el.receiptBooks.appendChild(row);
    });
}

async function openReceipt() {
    if (!state.sessionId) {
        return;
    }
    const storyTitle = (state.currentStory && state.currentStory.title) || '';
    el.receiptDate.textContent = formatNow();
    el.receiptBookTitle.textContent = (storyTitle + ' (창작본)').trim();
    el.receiptAuthor.textContent = el.authorNameInput.value.trim() || '이름 없는 꼬마 작가';
    el.receiptKeywords.textContent = state.keywords.length
        ? state.keywords.map((kw) => '#' + kw).join(' ')
        : '-';
    el.receiptBooksTitle.textContent = '[ 📚 추천 도서를 찾는 중... ]';
    clearChildren(el.receiptBooks);

    el.receiptModal.style.display = 'flex';

    try {
        const data = await api.getRecommendations(state.sessionId);
        const label = data.fallback ? '사서 추천 도서' : '아이의 생각과 닮은 책';
        el.receiptBooksTitle.textContent = '[ 📚 ' + label + ' ]';
        renderReceiptBooks(data.books);
    } catch (err) {
        console.error('failed to load recommendations', err);
        el.receiptBooksTitle.textContent = '[ 📚 추천 도서 ]';
        clearChildren(el.receiptBooks);
        const errEl = document.createElement('div');
        errEl.textContent = '추천 도서를 불러오지 못했어요.';
        el.receiptBooks.appendChild(errEl);
    }
}

function closeReceipt() {
    el.receiptModal.style.display = 'none';
}

/* ------------------------------------------------------------------ */
/* 처음으로                                                             */
/* ------------------------------------------------------------------ */

function goHome() {
    state.currentStory = null;
    state.sessionId = null;
    state.pages = [];
    state.keywords = [];
    el.authorNameInput.value = '';
    hidePdfError();
    clearChildren(el.pdfScrollBox);
    resetSpeechState();
    goTo('screen1');
}

/* ------------------------------------------------------------------ */
/* 초기화                                                              */
/* ------------------------------------------------------------------ */

function selectLang(lang) {
    state.lang = lang;
    goTo('screen2');
    loadStories();
}

function init() {
    el = {
        langKoBtn: document.getElementById('langKoBtn'),
        langEnBtn: document.getElementById('langEnBtn'),
        backToScreen1: document.getElementById('backToScreen1'),
        backToScreen2: document.getElementById('backToScreen2'),
        backToScreen3: document.getElementById('backToScreen3'),
        storyCount: document.getElementById('storyCount'),
        bookGrid: document.getElementById('bookGrid'),
        storyTitle: document.getElementById('storyTitle'),
        introSummary: document.getElementById('introSummary'),
        introImageWrap: document.getElementById('introImageWrap'),
        introImage: document.getElementById('introImage'),
        goScreen4Btn: document.getElementById('goScreen4Btn'),
        micBtn: document.getElementById('micBtn'),
        micUnsupportedNote: document.getElementById('micUnsupportedNote'),
        sttBox: document.getElementById('sttBox'),
        generateError: document.getElementById('generateError'),
        aiBtn: document.getElementById('aiBtn'),
        pdfScrollBox: document.getElementById('pdfScrollBox'),
        authorNameInput: document.getElementById('authorNameInput'),
        downloadPdfBtn: document.getElementById('downloadPdfBtn'),
        pdfError: document.getElementById('pdfError'),
        receiptBanner: document.getElementById('receiptBanner'),
        receiptModal: document.getElementById('receiptModal'),
        closeReceiptBtn: document.getElementById('closeReceiptBtn'),
        receiptDate: document.getElementById('receiptDate'),
        receiptBookTitle: document.getElementById('receiptBookTitle'),
        receiptAuthor: document.getElementById('receiptAuthor'),
        receiptKeywords: document.getElementById('receiptKeywords'),
        receiptBooksTitle: document.getElementById('receiptBooksTitle'),
        receiptBooks: document.getElementById('receiptBooks'),
        printLocationBtn: document.getElementById('printLocationBtn'),
        goHomeBtn: document.getElementById('goHomeBtn')
    };

    el.langKoBtn.addEventListener('click', () => selectLang('ko'));
    el.langEnBtn.addEventListener('click', () => selectLang('en'));

    el.backToScreen1.addEventListener('click', () => goTo('screen1'));
    el.backToScreen2.addEventListener('click', () => goTo('screen2'));
    el.backToScreen3.addEventListener('click', () => goTo('screen3'));

    el.goScreen4Btn.addEventListener('click', () => {
        resetSpeechState();
        goTo('screen4');
    });

    el.micBtn.addEventListener('click', toggleRecord);
    el.sttBox.addEventListener('input', () => {
        state.finalTranscript = el.sttBox.textContent;
        updateAiButtonState();
    });
    el.aiBtn.addEventListener('click', handleGenerate);

    el.downloadPdfBtn.addEventListener('click', handleDownloadPdf);

    el.receiptBanner.addEventListener('click', openReceipt);
    el.closeReceiptBtn.addEventListener('click', closeReceipt);
    el.printLocationBtn.addEventListener('click', () => {
        alert('징징징~ 🖨️\n도서관 프린터에서 청구기호표(위치표)가 출력되었습니다!\n책을 찾으러 서가로 이동해 보세요.');
    });

    el.goHomeBtn.addEventListener('click', goHome);

    initSpeechRecognition();
    updateAiButtonState();
}

document.addEventListener('DOMContentLoaded', init);
