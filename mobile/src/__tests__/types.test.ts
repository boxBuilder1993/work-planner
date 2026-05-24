import {
  TaskEntity,
  CommentEntity,
  DEFAULT_SEARCH_FILTERS,
  PRIORITY_COLORS,
} from '../types';

describe('Types', () => {
  it('should have valid default search filters', () => {
    expect(DEFAULT_SEARCH_FILTERS).toEqual({
      status: 'ALL',
      minPriority: 1,
      maxPriority: 5,
      dueDate: 'ANY',
    });
  });

  it('should have valid priority colors', () => {
    expect(PRIORITY_COLORS[1]).toBe('#E53935');
    expect(PRIORITY_COLORS[2]).toBe('#F57C00');
    expect(PRIORITY_COLORS[3]).toBe('#FDD835');
    expect(PRIORITY_COLORS[4]).toBe('#43A047');
    expect(PRIORITY_COLORS[5]).toBe('#1E88E5');
  });

  it('should allow creating TaskEntity objects', () => {
    const task: TaskEntity = {
      id: 'test-1',
      parentId: null,
      title: 'Test Task',
      description: 'Test Description',
      status: 'PENDING',
      priority: 3,
      dueDate: null,
      taskDate: null,
      plannedTime: null,
      duration: null,
      aiEnabled: false,
      props: {},
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    expect(task.title).toBe('Test Task');
    expect(task.status).toBe('PENDING');
  });

  it('should allow creating CommentEntity objects', () => {
    const comment: CommentEntity = {
      id: 'comment-1',
      taskId: 'task-1',
      text: 'This is a comment',
      parentCommentId: null,
      commentType: 'COMMENT',
      createdBy: 'user-1',
      proposalStatus: null,
      proposalFeedback: null,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    expect(comment.text).toBe('This is a comment');
    expect(comment.commentType).toBe('COMMENT');
  });
});
