// 파일 데이터 관리
let files = [];
let selectedFileId = null;
const API_BASE_URL = '/api';
const PDF_ICON_PATH = '/res/img/icon_pdf.png';

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    loadFiles();
    setupDragAndDrop();
    setupFileInput();
    setupResizer();
});

// stored_file_name 접두사로 파일 분류
function isCommonFile(storedFileName) {
    return storedFileName && storedFileName.startsWith('common_');
}

function isDocFile(storedFileName) {
    return storedFileName && storedFileName.startsWith('doc_');
}

function getCommonFiles() {
    return files.filter(f => isCommonFile(f.storedFileName));
}

function getDocFiles() {
    return files.filter(f => isDocFile(f.storedFileName));
}

// 파일 목록 로드 (백엔드 API 호출)
async function loadFiles() {
    try {
        const response = await fetch(`${API_BASE_URL}/documents`);
        if (response.ok) {
            const data = await response.json();




            // 확인좀
            // const data = await response.json();

            console.log("🔥 API 응답 데이터:", data);
            console.log("🔥 문서 개수:", data.length);

            // files = data





            files = data
                .filter(doc => isCommonFile(doc.stored_file_name) || isDocFile(doc.stored_file_name))
                .map(doc => ({
                    id: doc.doc_id,
                    name: doc.original_file_name,
                    storedFileName: doc.stored_file_name,
                    size: doc.file_size || 0,
                    modified: doc.created_at,
                    uploaded: doc.created_at,
                    vectorLoaded: doc.is_loaded,
                    vectorLoadedDate: doc.loaded_at,
                    loading: false
                }));
            renderAll();
        } else {
            console.error('Failed to load files:', response.statusText);
        }
    } catch (error) {
        console.error('Error loading files:', error);
    }
}

// 좌측 탐색기 + 우측 테이블 동시 렌더링
function renderAll() {
    renderFileList();
    renderFileTable();
    updatePanelSummary();
}

// 좌측 파일 탐색기 렌더링
function renderFileList() {
    const commonList = document.getElementById('commonFileList');
    const docList = document.getElementById('docFileList');
    const commonCount = document.getElementById('commonCount');
    const docCount = document.getElementById('docCount');

    commonList.innerHTML = '';
    docList.innerHTML = '';

    const commonFiles = getCommonFiles();
    const docFiles = getDocFiles();

    commonCount.textContent = commonFiles.length;
    docCount.textContent = docFiles.length;

    if (commonFiles.length === 0) {
        commonList.innerHTML = '<div class="list-empty">등록된 공통 법률이 없습니다</div>';
    } else {
        commonFiles.forEach(file => {
            commonList.appendChild(createFileItem(file));
        });
    }

    if (docFiles.length === 0) {
        docList.innerHTML = '<div class="list-empty">등록된 일반 문서가 없습니다</div>';
    } else {
        docFiles.forEach(file => {
            docList.appendChild(createFileItem(file));
        });
    }
}

// 우측 파일 테이블 렌더링
function renderFileTable() {
    renderTableSection('commonTableBody', 'commonEmptyMsg', 'commonFileTable', getCommonFiles());
    renderTableSection('docTableBody', 'docEmptyMsg', 'docFileTable', getDocFiles());
}

function renderTableSection(tbodyId, emptyMsgId, tableId, fileList) {
    const tbody = document.getElementById(tbodyId);
    const emptyMsg = document.getElementById(emptyMsgId);
    const table = document.getElementById(tableId);

    tbody.innerHTML = '';

    if (fileList.length === 0) {
        table.style.display = 'none';
        emptyMsg.style.display = 'block';
        return;
    }

    table.style.display = 'table';
    emptyMsg.style.display = 'none';

    fileList.forEach(file => {
        const row = document.createElement('tr');
        row.dataset.fileId = file.id;
        row.className = 'file-table-row';
        if (selectedFileId === file.id) {
            row.classList.add('active');
        }

        row.innerHTML = `
            <td class="col-icon">
                <img src="${PDF_ICON_PATH}" alt="PDF" class="table-pdf-icon">
            </td>
            <td class="col-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</td>
            <td class="col-size">${formatFileSize(file.size)}</td>
            <td class="col-date">${formatDate(file.uploaded)}</td>
            <td class="col-status">
                ${
                    file.loading
                    ? `<span class="status-badge not-loaded">로딩중...</span>`
                    : file.vectorLoaded
                        ? `<span class="status-badge loaded">적재완료</span>`
                        : `
                        <span class="status-badge not-loaded"
                            onclick="loadVector(${file.id}, this)">
                            <span class="normal-text">미적재</span>
                            <span class="hover-text">적재하기</span>
                        </span>
                        `
                }
            </td>
            <td class="col-date">${file.vectorLoadedDate ? formatDate(file.vectorLoadedDate) : '-'}</td>
        `;

        row.onclick = function() {
            selectFile(file.id);
        };

        tbody.appendChild(row);
    });
}

function updatePanelSummary() {
    const total = files.length;
    document.getElementById('panelSubtitle').textContent =
        `총 ${total}개 문서 (공통 법률 ${getCommonFiles().length} · 일반 ${getDocFiles().length})`;
}

// 파일 아이템 생성 (좌측 탐색기)
function createFileItem(file) {
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item';
    fileItem.dataset.fileId = file.id;

    if (file.loading) {
        fileItem.classList.add('loading');
    }

    if (selectedFileId === file.id) {
        fileItem.classList.add('active');
    }

    const iconDiv = document.createElement('div');
    iconDiv.className = 'file-icon';
    const iconImg = document.createElement('img');
    iconImg.src = PDF_ICON_PATH;
    iconImg.alt = 'PDF';
    iconDiv.appendChild(iconImg);

    const nameDiv = document.createElement('div');
    nameDiv.className = 'file-name';
    nameDiv.textContent = file.loading ? '업로드 중...' : file.name;
    nameDiv.title = file.name;

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.innerHTML = '×';
    deleteBtn.onclick = function(e) {
        e.stopPropagation();
        deleteFile(file.id);
    };

    fileItem.appendChild(iconDiv);
    fileItem.appendChild(nameDiv);
    fileItem.appendChild(deleteBtn);

    fileItem.onclick = function() {
        selectFile(file.id);
    };

    return fileItem;
}

// 파일 선택 (좌측·우측 동기화)
function selectFile(fileId) {
    selectedFileId = fileId;

    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.toggle('active', parseInt(item.dataset.fileId) === fileId);
    });

    document.querySelectorAll('.file-table-row').forEach(row => {
        row.classList.toggle('active', parseInt(row.dataset.fileId) === fileId);
    });

    const file = files.find(f => f.id === fileId);
    if (file) {
        document.getElementById('panelTitle').textContent = file.name;
    }
}

// 파일 삭제
async function deleteFile(fileId) {
    if (confirm('파일을 삭제하시겠습니까?')) {
        try {
            const response = await fetch(`${API_BASE_URL}/documents/${fileId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                const fileIndex = files.findIndex(f => f.id === fileId);
                if (fileIndex > -1) {
                    files.splice(fileIndex, 1);
                    renderAll();

                    if (selectedFileId === fileId) {
                        selectedFileId = null;
                        document.getElementById('panelTitle').textContent = '문서 목록';
                    }
                }
            } else {
                alert('파일 삭제에 실패했습니다.');
                console.error('Delete failed:', response.statusText);
            }
        } catch (error) {
            alert('파일 삭제에 실패했습니다.');
            console.error('Error deleting file:', error);
        }
    }
}

// 드래그 앤 드롭 설정
function setupDragAndDrop() {
    const uploadArea = document.getElementById('uploadArea');
    const uploadContent = uploadArea.querySelector('.upload-content');

    uploadContent.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadContent.classList.add('drag-over');
    });

    uploadContent.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadContent.classList.remove('drag-over');
    });

    uploadContent.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadContent.classList.remove('drag-over');

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length > 0) {
            handleFileUpload(droppedFiles[0]);
        }
    });

    uploadContent.addEventListener('click', function() {
        document.getElementById('fileInput').click();
    });
}

// 파일 인풋 설정
function setupFileInput() {
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
            fileInput.value = '';
        }
    });
}

// 파일 업로드 처리
async function handleFileUpload(file) {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        alert('PDF 파일만 업로드할 수 있습니다.');
        return;
    }

    const isDuplicate = files.some(f => f.name === file.name && !f.loading);
    if (isDuplicate) {
        alert('동일한 이름의 파일이 이미 존재합니다.');
        return;
    }

    const tempId = Date.now();
    const isCommon = file.name[0] && file.name[0].match(/\d/);
    const tempStoredName = isCommon ? `common_temp_${file.name}` : `doc_temp_${file.name}`;

    const newFile = {
        id: tempId,
        name: file.name,
        storedFileName: tempStoredName,
        size: file.size,
        modified: new Date(file.lastModified).toISOString(),
        uploaded: new Date().toISOString(),
        vectorLoaded: false,
        vectorLoadedDate: null,
        loading: true
    };

    files.push(newFile);
    renderAll();

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE_URL}/documents/upload`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const result = await response.json();
            const fileIndex = files.findIndex(f => f.id === tempId);
            if (fileIndex > -1) {
                files.splice(fileIndex, 1);
            }

            await loadFiles();
            const refreshedFile = files.find(f => f.id === result.doc_id);
            if (refreshedFile) {
                selectFile(refreshedFile.id);
            }
        } else {
            const error = await response.json();
            alert(`업로드 실패: ${error.detail || '알 수 없는 오류'}`);

            const fileIndex = files.findIndex(f => f.id === tempId);
            if (fileIndex > -1) {
                files.splice(fileIndex, 1);
                renderAll();
            }
        }
    } catch (error) {
        alert('업로드 중 오류가 발생했습니다.');
        console.error('Upload error:', error);

        const fileIndex = files.findIndex(f => f.id === tempId);
        if (fileIndex > -1) {
            files.splice(fileIndex, 1);
            renderAll();
        }
    }
}

async function loadVector(docId, element) {

    if (element.classList.contains("loading")) {
        return;
    }

    element.classList.add("loading");
    element.innerHTML = "적재중...";

    try {
        const response = await fetch(
            `/api/documents/${docId}/load`,
            {
                method: "PUT"
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail);
        }

        alert("벡터 적재 완료");

        await loadFiles();

    } catch(error) {

        console.error(error);
        alert("벡터 적재 실패 : " + error.message);

        element.classList.remove("loading");
        element.innerHTML = "적재하기";
    }
}

// HTML 이스케이프
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 파일 크기 포맷팅
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 날짜 포맷팅
function formatDate(dateString) {
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// 리사이저 설정
function setupResizer() {
    const resizer = document.getElementById('resizer');
    const fileExplorer = document.getElementById('fileExplorer');

    let startX, startWidth;

    resizer.addEventListener('mousedown', function(e) {
        startX = e.clientX;
        startWidth = fileExplorer.offsetWidth;
        resizer.classList.add('resizing');

        document.addEventListener('mousemove', resize);
        document.addEventListener('mouseup', stopResize);
    });

    function resize(e) {
        const dx = e.clientX - startX;
        const newWidth = startWidth + dx;

        if (newWidth >= 250 && newWidth <= 600) {
            fileExplorer.style.width = newWidth + 'px';
        }
    }

    function stopResize() {
        resizer.classList.remove('resizing');
        document.removeEventListener('mousemove', resize);
        document.removeEventListener('mouseup', stopResize);
    }
}
