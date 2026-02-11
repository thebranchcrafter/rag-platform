const API_BASE = '/api/v1';

// State
let documents = [];
let totalChunks = 0;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadDocuments();
    setupFileUpload();
});

// Load documents
async function loadDocuments() {
    const loadingEl = document.getElementById('loading');
    const gridEl = document.getElementById('documents-grid');
    const emptyEl = document.getElementById('empty-state');
    const errorEl = document.getElementById('error');

    loadingEl.classList.remove('hidden');
    gridEl.innerHTML = '';
    emptyEl.classList.add('hidden');
    errorEl.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/documents`);
        if (!response.ok) throw new Error('Failed to load documents');
        
        const data = await response.json();
        documents = data.documents;
        totalChunks = documents.reduce((sum, doc) => sum + doc.chunk_count, 0);

        updateStats(data.total, totalChunks);
        renderDocuments(documents);

        if (documents.length === 0) {
            emptyEl.classList.remove('hidden');
        }
    } catch (error) {
        errorEl.textContent = `Error loading documents: ${error.message}`;
        errorEl.classList.remove('hidden');
    } finally {
        loadingEl.classList.add('hidden');
    }
}

// Render documents
function renderDocuments(docs) {
    const gridEl = document.getElementById('documents-grid');
    gridEl.innerHTML = docs.map(doc => createDocumentCard(doc)).join('');
}

// Create document card HTML
function createDocumentCard(doc) {
    const date = new Date(doc.uploaded_at);
    const formattedDate = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });

    const icon = doc.file_type === 'pdf' ? '📄' : '📝';
    const typeColor = doc.file_type === 'pdf' ? '#ef4444' : '#3b82f6';

    return `
        <div class="document-card" data-id="${doc.id}">
            <div class="document-header">
                <div class="document-icon">${icon}</div>
                <div class="document-info">
                    <div class="document-name">${escapeHtml(doc.filename)}</div>
                    <span class="document-type" style="background: ${typeColor}15; color: ${typeColor}">
                        ${doc.file_type.toUpperCase()}
                    </span>
                </div>
            </div>
            <div class="document-meta">
                <div class="meta-item">
                    <span class="meta-icon">📊</span>
                    <span>${doc.chunk_count} chunk${doc.chunk_count !== 1 ? 's' : ''}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-icon">🕒</span>
                    <span>${formattedDate}</span>
                </div>
            </div>
            ${doc.metadata && Object.keys(doc.metadata).length > 0 ? `
            <div class="document-metadata">
                <div class="metadata-header">
                    <span class="meta-icon">🏷️</span>
                    <strong>Metadata:</strong>
                </div>
                <div class="metadata-content">
                    ${Object.entries(doc.metadata).map(([key, value]) => `
                        <div class="metadata-item">
                            <span class="metadata-key">${escapeHtml(key)}:</span>
                            <span class="metadata-value">${escapeHtml(typeof value === 'object' ? JSON.stringify(value) : String(value))}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            ` : ''}
            <div class="document-actions">
                <button class="btn btn-danger btn-sm" onclick="deleteDocument('${doc.id}')">
                    <span class="btn-icon">🗑️</span>
                    Delete
                </button>
            </div>
        </div>
    `;
}

// Update stats
function updateStats(totalDocs, totalChunks) {
    document.getElementById('total-docs').textContent = totalDocs;
    document.getElementById('total-chunks').textContent = totalChunks;
}

// Delete document
async function deleteDocument(id) {
    if (!confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/documents/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete document');
        }

        showToast('Document deleted successfully', 'success');
        loadDocuments();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Refresh documents
function refreshDocuments() {
    loadDocuments();
    showToast('Refreshing documents...', 'success');
}

// Upload modal
function showUploadModal() {
    document.getElementById('upload-modal').classList.remove('hidden');
    document.getElementById('file-input').value = '';
    document.getElementById('upload-progress').classList.add('hidden');
}

function hideUploadModal() {
    document.getElementById('upload-modal').classList.add('hidden');
    document.getElementById('upload-form').reset();
    document.getElementById('upload-progress').classList.add('hidden');
    // Reset metadata to default
    document.getElementById('metadata-input').value = '{}';
    // Reset file display
    const dropZone = document.getElementById('drop-zone');
    dropZone.innerHTML = `
        <span class="file-icon">📎</span>
        <p>Drag and drop a file here, or click to select</p>
        <p class="file-hint">Supports PDF and TXT files</p>
    `;
}

// File upload setup
function setupFileUpload() {
    const fileInput = document.getElementById('file-input');
    const dropZone = document.getElementById('drop-zone');
    const form = document.getElementById('upload-form');

    // Click to select file - now drop-zone is not inside label, so no double trigger
    dropZone.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        fileInput.click();
    });

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateFileDisplay(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            updateFileDisplay(e.target.files[0]);
        }
    });
}

function updateFileDisplay(file) {
    const dropZone = document.getElementById('drop-zone');
    dropZone.innerHTML = `
        <span class="file-icon">📎</span>
        <p><strong>${escapeHtml(file.name)}</strong></p>
        <p class="file-hint">${(file.size / 1024).toFixed(2)} KB</p>
    `;
}

// Handle upload
async function handleUpload(event) {
    event.preventDefault();
    
    const fileInput = document.getElementById('file-input');
    const metadataInput = document.getElementById('metadata-input');
    const uploadBtn = document.getElementById('upload-btn');
    const progressEl = document.getElementById('upload-progress');
    const progressFill = document.getElementById('progress-fill');

    // Manual validation instead of relying on HTML5 required (which doesn't work with hidden inputs)
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
        showToast('Please select a file', 'error');
        fileInput.focus(); // Try to focus (may not work if hidden, but we try)
        return;
    }

    // Validate metadata JSON
    let metadata = {};
    let metadataStr = '{}';
    
    // Get metadata input value - with fallback
    if (metadataInput) {
        metadataStr = metadataInput.value.trim() || '{}';
    }
    
    // Ensure we have a valid JSON object (default to empty object)
    if (!metadataStr || metadataStr === '') {
        metadataStr = '{}';
    }
    
    try {
        metadata = JSON.parse(metadataStr);
        if (typeof metadata !== 'object' || Array.isArray(metadata)) {
            throw new Error('Metadata must be a JSON object');
        }
    } catch (e) {
        showToast(`Invalid metadata JSON: ${e.message}`, 'error');
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    
    // Add file first
    formData.append('file', file);
    
    // ALWAYS append metadata - ensure it's a valid JSON string
    const metadataJson = JSON.stringify(metadata);
    console.log('Adding metadata to FormData:', metadataJson);
    formData.append('metadata', metadataJson);
    
    // Verify both fields were added
    const entries = Array.from(formData.entries());
    const hasFile = entries.some(([key]) => key === 'file');
    const hasMetadata = entries.some(([key]) => key === 'metadata');
    
    console.log('FormData entries:', entries.map(([k, v]) => [k, typeof v === 'string' ? v.substring(0, 50) : (v.name || 'File')]));
    
    if (!hasFile) {
        console.error('ERROR: file was not added to FormData!');
        showToast('Error: File field is missing', 'error');
        return;
    }
    
    if (!hasMetadata) {
        console.error('ERROR: metadata was not added to FormData!');
        showToast('Error: Metadata field is missing', 'error');
        return;
    }
    
    // Debug: log what we're sending
    console.log('Uploading file:', file.name, 'size:', file.size);
    console.log('Metadata string:', metadataJson);
    console.log('FormData entries:', Array.from(formData.entries()).map(([k, v]) => [k, typeof v === 'string' ? v : v.name]));

    uploadBtn.disabled = true;
    progressEl.classList.remove('hidden');
    progressFill.style.width = '30%';

    try {
        // Final verification before sending
        const finalEntries = Array.from(formData.entries());
        console.log('Final FormData before send:', finalEntries.map(([k, v]) => {
            if (typeof v === 'string') {
                return [k, v.length > 100 ? v.substring(0, 100) + '...' : v];
            } else if (v instanceof File) {
                return [k, `File: ${v.name} (${v.size} bytes)`];
            }
            return [k, String(v)];
        }));
        
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
            // Don't set Content-Type header - let browser set it with boundary for multipart/form-data
        });

        progressFill.style.width = '70%';

        if (!response.ok) {
            let errorMessage = 'Upload failed';
            try {
                const error = await response.json();
                errorMessage = error.detail || error.message || JSON.stringify(error);
            } catch (e) {
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }

        progressFill.style.width = '100%';
        const result = await response.json();

        setTimeout(() => {
            showToast('Document uploaded and processed successfully!', 'success');
            hideUploadModal();
            loadDocuments();
        }, 500);
    } catch (error) {
        showToast(`Upload failed: ${error.message}`, 'error');
        progressEl.classList.add('hidden');
    } finally {
        uploadBtn.disabled = false;
        progressFill.style.width = '0%';
    }
}

// Toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// Utility
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Close modal on outside click
document.getElementById('upload-modal').addEventListener('click', (e) => {
    if (e.target.id === 'upload-modal') {
        hideUploadModal();
    }
});
