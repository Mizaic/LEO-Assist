import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BenchmarkSetList } from '../BenchmarkSetList';
import * as api from '@/lib/api';

jest.mock('@/lib/api', () => ({
  getBenchmarkSets: jest.fn(),
  getBenchmarkRules: jest.fn(),
  deleteBenchmarkSet: jest.fn(),
  deleteBenchmarkRule: jest.fn(),
  runBenchmarkRule: jest.fn(),
}));

const mockRouter = { push: jest.fn() };
jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
}));

const sampleSets = [
  { id: 'ncda-2018', name: 'NCDA 2018', source: 'uploaded', audit_year: 2018 },
  { id: 'ncda-2019', name: 'NCDA 2019', source: 'uploaded', audit_year: 2019 },
];

describe('BenchmarkSetList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getBenchmarkSets as jest.Mock).mockResolvedValue(sampleSets);
    (api.getBenchmarkRules as jest.Mock).mockResolvedValue([]);
  });

  it('renders benchmark set names', async () => {
    render(<BenchmarkSetList />);
    expect(await screen.findByText('NCDA 2018')).toBeInTheDocument();
    expect(screen.getByText('NCDA 2019')).toBeInTheDocument();
  });

  it('navigates to detail page when row is clicked', async () => {
    render(<BenchmarkSetList />);
    const row = await screen.findByText('NCDA 2018');
    fireEvent.click(row.closest('tr')!);
    expect(mockRouter.push).toHaveBeenCalledWith('/benchmarks/sets/ncda-2018');
  });

  it('shows delete confirmation when delete button clicked', async () => {
    render(<BenchmarkSetList />);
    await screen.findByText('NCDA 2018');
    const deleteButtons = screen.getAllByLabelText('Delete benchmark set');
    fireEvent.click(deleteButtons[0]);
    expect(await screen.findByText(/permanently delete/i)).toBeInTheDocument();
  });

  it('calls deleteBenchmarkSet on confirmation', async () => {
    (api.deleteBenchmarkSet as jest.Mock).mockResolvedValue(undefined);
    render(<BenchmarkSetList />);
    await screen.findByText('NCDA 2018');
    const deleteButtons = screen.getAllByLabelText('Delete benchmark set');
    fireEvent.click(deleteButtons[0]);
    const confirmBtn = await screen.findByText('Delete');
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(api.deleteBenchmarkSet).toHaveBeenCalledWith('ncda-2018'));
  });

  it('shows empty state when no sets loaded', async () => {
    (api.getBenchmarkSets as jest.Mock).mockResolvedValue([]);
    render(<BenchmarkSetList />);
    expect(await screen.findByText(/No benchmark sets yet/i)).toBeInTheDocument();
  });

  it('navigates to upload page on Upload button click', async () => {
    render(<BenchmarkSetList />);
    await screen.findByText('NCDA 2018');
    fireEvent.click(screen.getByText('Upload'));
    expect(mockRouter.push).toHaveBeenCalledWith('/benchmarks/upload');
  });
});
