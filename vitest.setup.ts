import '@testing-library/jest-dom/vitest';

// jsdom doesn't implement scrollIntoView; ChatScreen calls it to keep the
// message list pinned to the bottom.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
