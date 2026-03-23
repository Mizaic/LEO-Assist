import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BenchmarkUploadWizard } from '../BenchmarkUploadWizard';
import * as api from '@/lib/api';

jest.mock('@/lib/api', () => ({
  uploadBenchmarks: jest.fn(),
  inferBenchmarkStructure: jest.fn(),
}));

const mockRouter = { push: jest.fn() };
jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
}));

const validJson = JSON.stringify({
  audit: { year: 2018, name: 'NCDA 2018' },
  entities: [{ id: 'nat', type: 'national', name: 'England' }],
  benchmarks: {},
});

describe('BenchmarkUploadWizard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.inferBenchmarkStructure as jest.Mock).mockResolvedValue({
      keys: ['audit', 'entities', 'benchmarks'],
      sample: {},
      depth: 2,
    });
  });

  it('renders step 0 (Upload) by default', () => {
    render(<BenchmarkUploadWizard />);
    expect(screen.getByText('Upload JSON')).toBeInTheDocument();
  });

  it('shows error for invalid JSON', () => {
    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: 'not-valid-json' } });
    expect(screen.getByText(/Invalid JSON/i)).toBeInTheDocument();
  });

  it('progresses to Inspect step after pasting valid JSON', async () => {
    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    expect(await screen.findByText(/Inspect Structure/i)).toBeInTheDocument();
  });

  it('progresses from Inspect to Map step', async () => {
    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    await screen.findByText(/Inspect Structure/i);
    fireEvent.click(screen.getByText('Next: Map'));
    expect(await screen.findByText(/Map to Schema/i)).toBeInTheDocument();
  });

  it('progresses from Map to Preview step (Save button appears)', async () => {
    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    await screen.findByText(/Inspect Structure/i);
    fireEvent.click(screen.getByText('Next: Map'));
    await screen.findByText(/Map to Schema/i);
    fireEvent.click(screen.getByText('Next: Preview'));
    // Step 3 shows a "Save" button and "Review the settings" text
    expect(await screen.findByText(/Review the settings/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('shows success screen after successful upload', async () => {
    (api.uploadBenchmarks as jest.Mock).mockResolvedValue({
      audit_id: 'ncda-2018',
      count: 120,
      status: 'completed',
    });

    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    await screen.findByText(/Inspect Structure/i);
    fireEvent.click(screen.getByText('Next: Map'));
    await screen.findByText(/Map to Schema/i);
    fireEvent.click(screen.getByText('Next: Preview'));
    await screen.findByText(/Review the settings/i);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/Upload successful/i)).toBeInTheDocument();
    expect(screen.getByText(/ncda-2018/)).toBeInTheDocument();
    expect(screen.getByText(/120/)).toBeInTheDocument();
  });

  it('navigates to set detail on "View set" after upload', async () => {
    (api.uploadBenchmarks as jest.Mock).mockResolvedValue({
      audit_id: 'ncda-2018',
      count: 120,
      status: 'completed',
    });

    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    await screen.findByText(/Inspect Structure/i);
    fireEvent.click(screen.getByText('Next: Map'));
    await screen.findByText(/Map to Schema/i);
    fireEvent.click(screen.getByText('Next: Preview'));
    await screen.findByText(/Review the settings/i);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText(/Upload successful/i);

    fireEvent.click(screen.getByText('View set'));
    expect(mockRouter.push).toHaveBeenCalledWith('/benchmarks/sets/ncda-2018');
  });

  it('shows error on upload failure', async () => {
    (api.uploadBenchmarks as jest.Mock).mockRejectedValue(new Error('Server error'));

    render(<BenchmarkUploadWizard />);
    const textarea = screen.getByPlaceholderText(/Paste benchmark JSON/i);
    fireEvent.change(textarea, { target: { value: validJson } });
    fireEvent.click(screen.getByText('Next: Inspect'));
    await screen.findByText(/Inspect Structure/i);
    fireEvent.click(screen.getByText('Next: Map'));
    await screen.findByText(/Map to Schema/i);
    fireEvent.click(screen.getByText('Next: Preview'));
    await screen.findByText(/Review the settings/i);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/Server error/i)).toBeInTheDocument();
  });
});
