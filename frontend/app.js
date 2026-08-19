document.addEventListener('DOMContentLoaded', () => {
    // Select elements
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const fileDetails = document.getElementById('fileDetails');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const removeFileBtn = document.getElementById('removeFileBtn');
    const translateBtn = document.getElementById('translateBtn');
    
    const loadingState = document.getElementById('loadingState');
    const loadingMessage = document.getElementById('loadingMessage');
    const successState = document.getElementById('successState');
    const downloadBtn = document.getElementById('downloadBtn');
    const resetBtn = document.getElementById('resetBtn');
    const errorState = document.getElementById('errorState');
    const errorMessage = document.getElementById('errorMessage');
    const closeErrorBtn = document.getElementById('closeErrorBtn');

    let selectedFile = null;
    let downloadBlob = null;
    let downloadName = '';

    // Drag and drop event listeners
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('border-blue-500', 'bg-blue-50/50');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('border-blue-500', 'bg-blue-50/50');
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    removeFileBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        resetUI();
    });

    resetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        resetUI();
    });

    closeErrorBtn.addEventListener('click', () => {
        errorState.classList.add('hidden');
    });

    // Handle file selection
    function handleFileSelect(file) {
        // Clear previous output states
        successState.classList.add('hidden');
        errorState.classList.add('hidden');
        downloadBlob = null;
        downloadName = '';

        // Validate extension
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext !== 'docx') {
            showError("Invalid file type. Only English Word Documents (.docx) are accepted.");
            return;
        }

        // Validate size (10 MB limit)
        const MAX_SIZE = 10 * 1024 * 1024;
        if (file.size > MAX_SIZE) {
            showError("File is too large. Maximum size allowed is 10 MB.");
            return;
        }

        selectedFile = file;
        
        // Show file details
        fileName.textContent = file.name;
        fileSize.textContent = formatBytes(file.size);
        
        fileDetails.classList.remove('hidden');
        dropzone.classList.add('hidden');
        
        // Enable translate button
        translateBtn.disabled = false;
    }

    // Reset UI to initial state
    function resetUI() {
        selectedFile = null;
        downloadBlob = null;
        downloadName = '';
        fileInput.value = '';
        
        fileDetails.classList.add('hidden');
        dropzone.classList.remove('hidden');
        translateBtn.disabled = true;
        
        loadingState.classList.add('hidden');
        successState.classList.add('hidden');
        errorState.classList.add('hidden');
    }

    // Trigger translate action
    translateBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        // Reset state
        translateBtn.disabled = true;
        removeFileBtn.disabled = true;
        loadingState.classList.remove('hidden');
        successState.classList.add('hidden');
        errorState.classList.add('hidden');
        
        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const response = await fetch('/translate', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                // Read error message from JSON response
                let errText = "An error occurred during translation.";
                try {
                    const errData = await response.json();
                    if (errData && errData.error) {
                        errText = errData.error;
                    }
                } catch (e) {
                    errText = `HTTP Error ${response.status}: ${response.statusText}`;
                }
                throw new Error(errText);
            }

            // Get blob data
            downloadBlob = await response.blob();
            
            // Try to extract filename from content-disposition header
            const disposition = response.headers.get('content-disposition');
            if (disposition && disposition.indexOf('attachment') !== -1) {
                const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                const matches = filenameRegex.exec(disposition);
                if (matches != null && matches[1]) { 
                    downloadName = matches[1].replace(/['"]/g, '');
                }
            }
            
            if (!downloadName) {
                const origName = selectedFile.name.replace(/\.[^/.]+$/, "");
                downloadName = `${origName}_marathi.docx`;
            }

            // Display success
            loadingState.classList.add('hidden');
            successState.classList.remove('hidden');
            removeFileBtn.disabled = false;

            // Optional auto download
            triggerDownload();

        } catch (error) {
            console.error(error);
            showError(error.message);
            loadingState.classList.add('hidden');
            translateBtn.disabled = false;
            removeFileBtn.disabled = false;
        }
    });

    // Trigger file download
    downloadBtn.addEventListener('click', () => {
        triggerDownload();
    });

    function triggerDownload() {
        if (!downloadBlob) return;
        
        const url = window.URL.createObjectURL(downloadBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = downloadName;
        document.body.appendChild(a);
        a.click();
        
        // Clean up
        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }, 100);
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorState.classList.remove('hidden');
    }

    // Bytes formatting utility
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
