window.uploadCmsImage = async function (file, options) {
  const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
  const maxSize = 5 * 1024 * 1024;
  const input = options.input;
  const setStatus = options.setStatus || function () {};

  if (!file) {
    setStatus('Please select an image.');
    return '';
  }
  if (!allowedTypes.includes(file.type)) {
    setStatus('Only JPG, JPEG, PNG and WebP images are allowed.');
    return '';
  }
  if (file.size > maxSize) {
    setStatus('Image must be 5 MB or smaller.');
    return '';
  }

  const body = new FormData();
  body.append('file', file);
  input.disabled = true;
  setStatus('Uploading image...');
  try {
    const response = await fetch(options.endpoint, {
      method: 'POST',
      body,
      credentials: 'same-origin'
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.success || !result.url) {
      throw new Error(result.detail || 'Image upload failed.');
    }
    setStatus('Image uploaded.');
    return result.url;
  } catch (error) {
    setStatus(error.message || 'Image upload failed.');
    return '';
  } finally {
    input.disabled = false;
    input.value = '';
  }
};
